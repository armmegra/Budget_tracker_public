"""Hands the configuration file to another app, and takes one back."""

from __future__ import annotations

from words import t

MESSENGERS = {
    "Telegram": ("org.telegram.messenger", "org.telegram.messenger.web",
                 "org.thunderdog.challegram"),
    "WhatsApp": ("com.whatsapp", "com.whatsapp.w4b"),
}


class NotHere(Exception):
    pass


KINDS = {"json": "application/json", "txt": "text/plain"}


def kind_of(name: str) -> str:
    return KINDS.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def send(messenger: str, name: str, data: bytes) -> None:
    try:
        from jnius import JavaException, autoclass, cast
    except ImportError:
        raise NotHere(t("send.notphone", "Sending to a messenger works on the phone.")) from None

    activity = autoclass("com.flet.serious_python_android.PythonActivity").mActivity
    context = cast("android.content.Context", activity)

    File = autoclass("java.io.File")
    folder = File(context.getCacheDir(), "share_plus")
    folder.mkdirs()
    target = File(folder, name)
    with open(target.getAbsolutePath(), "wb") as out:
        out.write(data)

    FileProvider = autoclass("androidx.core.content.FileProvider")
    address = FileProvider.getUriForFile(
        context, context.getPackageName() + ".flutter.share_provider", target)

    Intent = autoclass("android.content.Intent")
    ClipData = autoclass("android.content.ClipData")
    intent = Intent(Intent.ACTION_SEND)
    intent.setType(kind_of(name))
    intent.putExtra(Intent.EXTRA_STREAM, cast("android.os.Parcelable", address))
    intent.setClipData(ClipData.newRawUri(name, address))
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    for package in MESSENGERS[messenger]:
        intent.setPackage(package)
        try:
            context.startActivity(intent)
            return
        except JavaException:
            continue
    raise NotHere(t("send.missing", "{messenger} is not installed on this phone.",
                    messenger=messenger))
