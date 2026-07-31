# Deploy Medication Dashboard on Any Machine

This guide explains how to run **MedicationDashboard.exe** on a Windows PC that does not have Python or Node.js installed.

## What You Need

- **Windows 10 or 11**
- The contents of the `dist` folder after building (see below)
- A browser (Chrome, Edge, Firefox)

## Quick Start (After Building)

1. **Copy the whole `dist` folder** to the target machine (e.g. USB drive or network share).
2. **Create `.env`** in the same folder as `MedicationDashboard.exe`:
   - Copy `dist\.env.example` to `dist\.env`
   - Edit `.env` and set at least:
     - `PORT=5000` (or another free port)
     - `EXCEL_PATH=./Data/patients.xlsx` (or full path to your Excel file)
     - Add API keys if you use notifications (OpenAI, Pushover, Twilio, SendGrid). Leave blank to run without those features.
3. **Put your data file** `patients.xlsx` in the `Data` folder inside the same folder as the exe (or set `EXCEL_PATH` in `.env` to point to it).
4. **Run** `MedicationDashboard.exe`. A console window will open.
5. **Open in browser:** `http://localhost:5000` (or `http://localhost:PORT` if you changed PORT).

## Folder Layout on Target Machine

```
YourFolder/
  MedicationDashboard.exe   <- run this (single file, no Python needed)
  .env                     <- copy from .env.example, then edit
  .env.example
  Data/
    patients.xlsx          <- your patient data (or set EXCEL_PATH in .env)
  DEPLOY.md                <- this file (optional)
```

## If Something Goes Wrong

- **"Port already in use"**  
  Set `PORT=5001` (or another number) in `.env`. The app will try the next free port automatically.

- **"No patient data" / empty dashboard**  
  When you run the exe, the console shows: **Data file: &lt;full path&gt;**  
  Put `patients.xlsx` in that folder (the `Data` folder next to the exe), or set `EXCEL_PATH` in `.env` to your file. The dashboard will also show the expected path in a blue banner until the file is found.

- **"Twilio credentials not configured" / "Twilio voice credentials not configured"**  
  The app loads `.env` from **(1) the folder where the exe lives** and **(2) the folder you run the exe from**. Put a `.env` file in the **same folder as MedicationDashboard.exe** (e.g. copy `.env.example` to `.env` there). Edit `.env` and set:  
  `TWILIO_ACCOUNT_SID=...`, `TWILIO_AUTH_TOKEN=...`, `TWILIO_FROM_NUMBER=+1...`  
  No spaces around `=`. Restart the exe after saving. If you run the exe from your project folder, a `.env` in that folder is also read.

- **Antivirus blocks the exe**  
  Some antivirus software may flag PyInstaller exes. Add an exception for the folder or the exe, or build on the target machine.

- **Firewall**  
  If others on the network should access the dashboard, allow inbound TCP for the port (e.g. 5000) in Windows Firewall.

## Building the Exe (Developer Machine)

On a machine with Python and Node.js:

1. Open a terminal in the project root.
2. Run: `build_exe.bat`
3. When it finishes, use the `dist` folder as described above.

No Python or Node.js is required on the machine where you only run the exe.
