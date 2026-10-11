# HR Employee Analytics Dashboard

A Windows app for exploring employee data: a dashboard of key numbers and charts,
custom charts, forecasts, and an AI Advisor that answers questions about the data.
Everything runs on your own computer; no employee data is sent anywhere.

---

## Put the app on your desktop

There are two ways, depending on what you have.

### A) Someone gave you the app file (`HR_Analytics_Dashboard.exe`)

1. Move the file somewhere it can stay, for example your **Documents** folder.
2. Right-click the file → **Send to** → **Desktop (create shortcut)**.
   (On Windows 11, click **Show more options** first to see **Send to**.)
3. Double-click the new shortcut on your desktop to open the app.

That's it. You can skip the rest of this page except **The AI Advisor** below.

### B) You have the project files and want to build the app yourself

You only need to do steps 1 and 2 once.

**Step 1: Install Python (one time only)**

1. Go to **https://www.python.org/downloads/windows/**.
2. Find **Python 3.12.10** and click **Windows installer (64-bit)**.
   Newer versions (3.13, 3.14) will **not** work with this app, so pick 3.12.
3. Open the downloaded file. On the first screen, tick
   **"Add python.exe to PATH"**, then click **Install Now**.

**Step 2: Get the project files**

- From GitHub: click the green **Code** button → **Download ZIP**, then
  right-click the downloaded ZIP → **Extract All**.
- Or use the project folder you were given.

**Step 3: Build the app**

1. Open the project folder, then the **HR Analytics Dashboard** folder inside it.
2. Double-click **`build_exe.bat`**.
   - If Windows shows **"Windows protected your PC"**, click **More info** → **Run anyway**.
3. A black window opens and shows its progress. Leave it running.
   - The **first time** takes about 5–10 minutes (it downloads what the app needs).
   - After that it takes about 2 minutes.
4. When it says **Done!**, press any key to close the window.

An **HR Analytics Dashboard** icon is now on your desktop. Double-click it to open
the app. It takes a few seconds to start.

> The desktop icon opens the app from the project's `dist` folder, so don't delete
> or move the project folder. To share the app with someone else, give them
> `HR Analytics Dashboard\dist\HR_Analytics_Dashboard.exe` and point them to option A.

---

## Updating the app

After the project files change, double-click **`build_exe.bat`** again. The desktop
icon will open the new version.

---

## The AI Advisor

The first time you open the **AI Advisor** tab, it will ask to download its AI model.
Click **Download Model**. It's about 2 GB and only downloads once, so use a
good internet connection.

If you already have the model file (`Llama-3.2-3B-Instruct-Q4_K_M.gguf`), you can
skip the download. Make a folder called **`models`** next to
`HR_Analytics_Dashboard.exe`, put the file in it, then click **Check Again**.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| "Python 3.9 - 3.12 was not found" | Do **Step 1** again. Make sure you install **3.12** (not 3.13 or 3.14) and tick **"Add python.exe to PATH"**. |
| "Windows protected your PC" | Click **More info** → **Run anyway**. |
| It fails while downloading | Check your internet connection, then double-click `build_exe.bat` again. |
| It still fails during setup | Delete the **`env`** folder inside **HR Analytics Dashboard**, then double-click `build_exe.bat` again to start fresh. |
| Your antivirus blocks or removes the app | This can happen with apps built this way. Allow it in your antivirus settings. |
| The desktop icon stopped working | The project folder was probably moved. Double-click `build_exe.bat` again to fix the icon. |

---

## For developers

After `build_exe.bat` has set up the `env` folder once, from the
`HR Analytics Dashboard` folder:

```
env\Scripts\activate
python HR_Analytics_Dashboard.py      # run the app from source
pytest tests/ -v                      # run the tests
```

The build settings are in `HR_Analytics_Dashboard.spec`.
