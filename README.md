# M59 Companion

A lightweight, multi-instance companion tool for Meridian 59 designed to automate character tracking, progression math, and tactical awareness.

[**Download Latest Release (EXE)**](https://github.com/subvhome/m59-companion/raw/main/dist/M59Companion.exe)

---

## Screen Showcases

### Main Dashboard
![Main Dashboard Interface](demo/main.gif)
*Overview of the primary tactical HUD, including HP/MP/VG monitoring and session statistics.*

### Live Tracker
![Live Tracker](demo/tracker.gif)
*Real-time tracking of skill gains, hit point improvements, and session kill counts.*

### PK Alert System
![PK Alert](demo/PVP%20alert.gif)
*I USED THE RAT IN THIS DEMO -- Configurable alerts that trigger when non-mob entities attack you. Works even when the app is in the background.*

### Vault Manager
![Vault Manager](demo/Vault%20Management.gif)
*Automated inventory scanning for the Barloque Vault. High-density dual-pane view for remote storage tracking.*

---

## Core Features

### 1. Tactical HUD (Dashboard)
*   **Live Vitals:** Raw values for HP, MP, and VG refreshed every 10 seconds.
*   **Static Attributes:** Instant view of Might, Intellect, Stamina, Agility, Mysticism, Aim, and Karma.
*   **Session Gains:** Real-time list of every skill improved during your current session.
*   **Quick Kills:** Dedicated column for monster and player kills in the current run.
*   **Stable Layout:** A persistent footer status bar and reinforced UI that maintains visibility even when shrinking the window.

### 2. Unified Communications Center
*   **Combat Subtraction Filter:** Uses high-efficiency logic (derived from the official Blakod source) to strip battle spam from your social feed.
*   **Real-time Channels:** Automatic sorting of incoming text into dedicated channels:
    *   **Clean Feed:** Social and System messages only.
    *   **Tells:** Dedicated Private Message tracker.
    *   **Broadcasts:** Global chat and Yells.
    *   **Social:** Local 'Says' and Emotes.
*   **Historical Log Browser:** Integrated directly into the comms center; switch between live feeds and your entire log library without leaving the tab.

### 3. The Kill Book (Eternal Trophies)
*   **Historical Tally:** Persistent tracking of every creature and player you've ever slain.
*   **Dual Pane:** Separate lists for Monsters vs. Players & Notables.
*   **Comprehensive Database:** Includes rare variants (Xeochicatls, Skeletons, etc.) and "dead state" detection.

### 4. Live Population Tracker (Who List)
*   **Integrated Sidebar:** A real-time list of online players visible directly in the dashboard.
*   **Desktop Docking:** Pop the Who List out of the main window and dock it to the side of your screen for a persistent "at-a-glance" view.
*   **Automatic Updates:** Silently monitors server population without interrupting your gameplay.

### 5. School Progression (Calculator)
*   **Target Sums:** Uses the standard server advancement formula to show exactly what % sum you need for your next rank.
*   **Tab Dance:** One-click automation to cycle your in-game tabs and refresh all knowledge.
*   **Intellect Scaling:** Dynamically adjusts "Points Needed" based on your character's current Intellect.

### 6. Vault Management
*   **Automated Scanning:** Sends 'withdraw' commands and clicks through your vault to refresh quantities.
*   **Dual Storage:** Dedicated support for Barloque and Hungry Vaults.
*   **Instant Filter:** Search through large inventories instantly as you type.

---

## UI & Customization
*   **Draggable Tabs:** A fully modular interface—click and drag any tab header to rearrange the dashboard layout to fit your workflow.
*   **Orderly Startup:** A prioritized initialization sequence that handles updates and identity verification before loading heavy profile data, ensuring a lag-free experience.
*   **Persistent Monitoring:** The chat and stat monitors automatically re-bind to the game client even after character logouts or reloads.

---

## Diagnostic & Alert Tools
*   **PK Alert System:** Configurable alarms (Sound + Visual Red Frame) that trigger when non-mob entities attack you. Now immune to fake '/emote' pranks via color-intent filtering.
*   **World Map & GPS Discovery:** (Experimental) A live log of your movement across the world. Discover new rooms and track transitions as you travel.
*   **Verbose Debug Mode:** A toggleable developer console that logs raw scraper data and internal progression calculations to both the terminal and `logs/companion_debug.log`.

---

## Alert Settings
Customize how you want to be notified of threats:
*   **Global Toggle:** Enable or disable all PK alerts.
*   **Custom Alarm:** Select any `.wav` file as your alarm sound.
*   **Red Frame:** A thick visual bracket appears around your game window when attacked.

---

## Coming Soon
*   **GPS Navigation:** Select a destination and receive turn-by-turn directions as you move across screens.
*   **Shortcut Keys:** Assign custom key combinations or mouse buttons to execute complex in-game actions.

---

## Feedback & Suggestions
We are always looking for ways to improve the Companion. If you have ideas or bug reports, please mail **MF DOOM** in-game with your suggestions.

*Created for the Meridian 59 community.*
