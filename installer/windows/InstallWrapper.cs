using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

internal static class InstallWrapper
{
    [STAThread]
    private static int Main(string[] args)
    {
        string directory = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string installer = Path.Combine(directory, "Install-Kabuki-Cord.cmd");

        if (!File.Exists(installer))
        {
            MessageBox.Show(
                "Install-Kabuki-Cord.cmd was not found next to this installer. Extract the full Kabuki-Cord ZIP, then run the installer again.",
                "Kabuki-Cord Installer",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }

        ProcessStartInfo startInfo = new ProcessStartInfo
        {
            FileName = installer,
            WorkingDirectory = directory,
            UseShellExecute = true,
            Arguments = JoinArguments(args)
        };
        Process.Start(startInfo);
        return 0;
    }

    private static string JoinArguments(string[] args)
    {
        if (args == null || args.Length == 0)
        {
            return "";
        }

        string[] quoted = new string[args.Length];
        for (int i = 0; i < args.Length; i++)
        {
            quoted[i] = "\"" + args[i].Replace("\"", "\\\"") + "\"";
        }
        return string.Join(" ", quoted);
    }
}
