// budget.exe - the thing you double-click.
//
// Finds a Python, runs serve.py beside this file with it, and keeps the window
// open if that fails so the reason can be read. It installs nothing, writes
// nothing, and never reaches the internet - a batch file's whole job, done
// by something Windows users recognise as an application.
//
// Every line it prints comes in English and then in Russian: which language
// the person reads is chosen later, in the browser, where this cannot see it.
// So the console is switched to UTF-8 - the Russian then arrives whole on the
// screen and down a pipe alike - and this file is saved as UTF-8, which
// build.py tells the compiler.
//
// Where it looks for Python, in order:
//
//   1. vendor\python\python.exe   the private copy fetch_runtime.py puts there
//                                 (the packaged copy ships with it). Present,
//                                 the folder needs nothing installed.
//   2. python.exe on PATH         whatever the machine has - except the
//                                 Microsoft Store stub. Windows 10 and 11 put a
//                                 zero-byte python.exe on PATH whether or not
//                                 Python is installed, and running it opens the
//                                 Store. A plain `where python` finds that
//                                 stub and reports success; this does not.
//
// Built by launcher\build.py with the C# compiler that every Windows ships as
// part of the .NET Framework, so there is no toolchain to install. Do not edit
// budget.exe; edit this and rebuild.

using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;

[assembly: AssemblyTitle("Budget tracker")]
[assembly: AssemblyDescription("Starts the budget tracker on this computer and opens it in your browser.")]
[assembly: AssemblyProduct("Budget tracker (local build)")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

static class Budget
{
    static int Main(string[] args)
    {
        // UTF-8, with no byte-order mark. A start with no console at all
        // (DETACHED_PROCESS) has none to switch: the setter throws there, and
        // that start keeps the default encoding rather than failing.
        try { Console.OutputEncoding = new UTF8Encoding(false); }
        catch (IOException) { }

        string here = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(here, "serve.py");

        if (!File.Exists(script))
        {
            Console.WriteLine();
            Console.WriteLine("  serve.py is not beside budget.exe.");
            Console.WriteLine("  This launcher belongs in the budget tracker folder, next to serve.py.");
            Console.WriteLine("  serve.py нет рядом с budget.exe.");
            Console.WriteLine("  Этот файл запуска должен лежать в папке приложения, рядом с serve.py.");
            Console.WriteLine();
            Pause();
            return 1;
        }

        string python = FindPython(here);
        if (python == null)
        {
            Console.WriteLine();
            Console.WriteLine("  No Python found.");
            Console.WriteLine("  Python не найден.");
            Console.WriteLine();
            // fetch_runtime.py is in the developer's copy only; the packaged
            // copy ships vendor\ filled, so a copy without it is told to
            // download the app again rather than to run a file it lacks.
            if (File.Exists(Path.Combine(here, "fetch_runtime.py")))
            {
                Console.WriteLine("  Either install Python 3.11 or newer from python.org,");
                Console.WriteLine("  or run this once on a machine with internet:");
                Console.WriteLine("  Установите Python 3.11 или новее с сайта python.org");
                Console.WriteLine("  или один раз выполните на компьютере с интернетом:");
                Console.WriteLine();
                Console.WriteLine("      python fetch_runtime.py");
                Console.WriteLine();
                Console.WriteLine("  which puts a private copy in vendor\\ so this folder needs nothing installed.");
                Console.WriteLine("  — эта команда положит собственную копию в vendor\\,");
                Console.WriteLine("  и этой папке не понадобится ничего устанавливать.");
            }
            else
            {
                Console.WriteLine("  Either install Python 3.11 or newer from python.org,");
                Console.WriteLine("  or download the app again: it comes with a private copy in vendor\\");
                Console.WriteLine("  so this folder needs nothing installed.");
                Console.WriteLine("  Установите Python 3.11 или новее с сайта python.org");
                Console.WriteLine("  или скачайте приложение заново: в нём есть собственная копия в vendor\\,");
                Console.WriteLine("  и этой папке не понадобится ничего устанавливать.");
            }
            Console.WriteLine();
            Pause();
            return 1;
        }

        // Ctrl-C reaches every process sharing this console. Let the server
        // handle it - it prints "stopped" and exits cleanly - rather than
        // dying here first and leaving its farewell unread.
        Console.CancelKeyPress += delegate(object sender, ConsoleCancelEventArgs e) { e.Cancel = true; };

        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = python;
        start.Arguments = Quote(script) + JoinArgs(args);
        start.WorkingDirectory = here;
        start.UseShellExecute = false;

        int code;
        try
        {
            using (Process server = Process.Start(start))
            {
                server.WaitForExit();
                code = server.ExitCode;
            }
        }
        catch (Exception why)
        {
            Console.WriteLine();
            Console.WriteLine("  Could not start " + python);
            Console.WriteLine("  Не удалось запустить " + python);
            Console.WriteLine("  " + why.Message);
            Console.WriteLine();
            Pause();
            return 1;
        }

        if (code != 0)
        {
            Console.WriteLine();
            Console.WriteLine("  The server stopped with an error. The message above says why.");
            Console.WriteLine("  Сервер остановился с ошибкой. Причина — в сообщении выше.");
            Console.WriteLine();
            Pause();
        }
        return code;
    }

    static string FindPython(string here)
    {
        string bundled = Path.Combine(Path.Combine(Path.Combine(here, "vendor"), "python"), "python.exe");
        if (File.Exists(bundled)) return bundled;

        string path = Environment.GetEnvironmentVariable("PATH");
        if (path == null) return null;
        foreach (string dir in path.Split(Path.PathSeparator))
        {
            if (dir.Length == 0) continue;
            if (dir.IndexOf("WindowsApps", StringComparison.OrdinalIgnoreCase) >= 0) continue;
            string candidate;
            try { candidate = Path.Combine(dir, "python.exe"); }
            catch (ArgumentException) { continue; }        // a PATH entry with characters a path cannot hold
            if (File.Exists(candidate)) return candidate;
        }
        return null;
    }

    static string Quote(string s)
    {
        return "\"" + s + "\"";
    }

    static string JoinArgs(string[] args)
    {
        StringBuilder sb = new StringBuilder();
        foreach (string a in args) sb.Append(' ').Append(Quote(a));
        return sb.ToString();
    }

    static void Pause()
    {
        Console.WriteLine("  Press any key to close this window.");
        Console.WriteLine("  Нажмите любую клавишу, чтобы закрыть это окно.");
        try { Console.ReadKey(true); }
        catch (InvalidOperationException) { }              // no keyboard: input is a pipe
    }
}
