# What is bundled

This app comes with two programs that other people wrote: a Python interpreter,
which runs the app, and Tesseract, the OCR engine behind *Read screenshot(s)*,
with the two language models it reads English and Russian with. All of it is
in `vendor/`. This page says what they are and which licences they come under.

*This describes the licences involved. It is not legal advice.*

---

## Python 3.13.1, embeddable build

**Source:** python.org, `python-3.13.1-embed-amd64.zip`
**Licence:** PSF License Agreement Version 2, in `vendor/python/LICENSE.txt`

The PSF licence grants a "nonexclusive, royalty-free, world-wide license to
reproduce, analyze, test, perform and/or display publicly, prepare derivative
works, distribute, and otherwise use Python" - on the condition that the licence
and the PSF copyright notice are retained. They are, in
`vendor/python/LICENSE.txt`.

Bundling a Python interpreter with an application is ordinary and expected; it
is what the embeddable distribution exists for.

---

## Tesseract 5.4.0 and its support libraries

**Source:** the UB-Mannheim Windows build, which is the standard one
**Tesseract's own licence:** Apache 2.0, in `vendor/tesseract/LICENSE`

Tesseract itself is under Apache 2.0, which permits redistribution provided the
licence travels with it. It does, in `vendor/tesseract/LICENSE`.

An OCR engine needs image and compression libraries, and 26 of them are bundled
beside it. They come from the MSYS2 project's builds, and the installer they
came from ships no licence texts for them - only Tesseract's own. They are, in
full:

```
libtesseract-5  libleptonica-6  libarchive-13   libcrypto-3-x64  libexpat-1
libtiff-6       libjpeg-8       libpng16-16     libwebp-7        libwebpmux-3
libsharpyuv-0   libopenjp2-7    libgif-7        liblerc          libjbig-0
libdeflate      libzstd         liblzma-5       libbz2-1         liblz4
zlib1           libiconv-2      libb2-1         libstdc++-6      libgcc_s_seh-1
libwinpthread-1
```

**Most are permissive** - BSD, MIT, zlib and Apache-style licences that ask only
for attribution. That covers the image formats, the compressors, OpenSSL and
Leptonica.

**Two are under other terms:**

- **`libiconv-2`** - GNU libiconv is under the LGPL. The LGPL allows exactly this
  arrangement: a separate shared library, loaded at run time, beside a program
  under any licence. It asks that its use is stated, that its licence is
  available, and that nothing prevents replacing the DLL with another build of
  it. It is a standalone `.dll` file here, and can be replaced.
- **`libjbig-0`** - jbig-kit is, in its usual distribution, under the GPL. It is
  here because `libtiff` was built with JBIG support, not because the app uses
  it: the app reads PNG and JPEG screenshots and never a JBIG-compressed TIFF.

Nothing in the app links against any of these libraries. It runs
`tesseract.exe` as a **separate program**: the screenshot goes in on its
standard input and the text comes back on its standard output. The app and the
OCR engine communicate as two programs, not as one linked binary.

---

## The Russian language model

**Source:** the Tesseract project's `tessdata_fast` repository, release 4.1.0,
`rus.traineddata` (3.9 MB)
**Licence:** Apache 2.0, in `vendor/tesseract/LICENSE` - the same text as the
repository's own `LICENSE` file

`vendor/tesseract/tessdata/` holds two language models. `eng.traineddata` came
with Tesseract's installer; `rus.traineddata` was downloaded on its own,
because the installer carries no other language. Both come from the same
release of the same repository, both are data the engine reads rather than
programs, and both are here exactly as they were published.

Screenshots are read with the Russian model while the Russian example
household is in place. The English example household reads them in English.

---

## What was modified

The OCR engine in `vendor/tesseract/` is not exactly as it was published:

- only `tesseract.exe`, the 26 libraries it actually loads, and the English
  language data are kept; the training tools, and the 36 MB of ICU tables that
  only those tools use, were left out;
- the DWARF debug sections and the symbol table were removed from each binary,
  which takes `libtesseract-5.dll` from 101 MB to 3 MB;
- the Russian language data was added beside the English, unmodified.

Removing debug symbols changes nothing the engine runs: the stripped engine was
checked against the unmodified build over the same image and read it
identically. But the binaries in `vendor/` are not byte-for-byte what
UB-Mannheim published, and that is said here. The originals are UB-Mannheim's
Tesseract 5.4.0 release for Windows.

---

## Nothing else is bundled

No fonts, no JavaScript libraries, no CSS frameworks. The page is one HTML file
that loads nothing from anywhere else. `budget.exe`, the launcher, and its icon
were made for this app, not taken from anyone else.
