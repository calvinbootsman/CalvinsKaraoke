# Calvin's Karaoke

Calvin's Karaoke is a web application that allows you to sing your favourite songs with karaoke tracks. It uses AI to remove vocals from songs and provides a seamless karaoke experience. Find your song on Youtube, add it to the queue, and start singing! This works for songs that don't have a karaoke track available, or if you just want to sing along to your favourite songs. 

Built with Streamlit, Calvin's Karaoke downloads your requested songs, separates vocals using AI (Demucs), extracts pitch data (Torchcrepe), and fetches synchronized lyrics to create a complete, interactive karaoke player complete with a dual-window UI and responsive controls.

---

## 🎵 Features
![Singing interface](images/pop_up_window.png)
* **YouTube Ingestion:** Simply paste a YouTube URL to download the audio track.
* **AI Stem Separation:** Uses Demucs (MDX Extra model) to automatically remove vocals and provide a clean instrumental track.
* **Pitch Extraction:** Powered by `torchcrepe` to extract, cleanly quantize, and visualize accurate pitch lines for real-time sing-along (with adjustable confidence thresholds).
* **Real-Time Pitch Feedback:** Not only can you see the original track's pitch, but the player also visualizes the pitch you are currently singing, giving you immediate real-time feedback on your performance!
* **Synchronized Lyrics:** Automatically fetches LRC formatted lyrics via `syncedlyrics` mapped precisely to the audio.
* **Dedicated Player Window:** Detach the karaoke player to a pop-out dual-screen friendly window. Seamlessly updates with lyrics, current playback time, and dynamic pitch visualization via a robust BroadcastChannel and LocalStorage bridge.
* **Non-Blocking Processing:** Start playing music from your "Saved" tab while new songs are downloading, separating, and processing into stems in the background. Track processing with live progress bars.
* **Queue Management:** Drag-and-drop to reorder songs! Add, remove, and skip tracks seamlessly.
* **Fuzzy Search:** Easily search through your saved library using fuzzy text matching.

---

## 🏗️ Architecture Flow

1. **Ingestion & Processing (Background Task)**
   `YouTube URL` ➔ `yt-dlp (Download)` ➔ `Demucs (Stem Separation)` & `syncedlyrics (Fetch LRC)` & `torchcrepe (Extract Pitch)` -> Saved to `./music/`

2. **Playback Engine & Queue State**
   The main UI manages session queue state, while a persistent multithreading HTTP Media Server serves the files from the `./music/` directory dynamically to avoid locking paths.

3. **Bridge Communication**
   The browser bridges the Streamlit controller with the dedicated Karaoke window popup using HTML5 `BroadcastChannel` and `LocalStorage`—providing low-latency updates for Play/Pause, scrubbing, and skipping without reloading Streamlit.

---

## 📦 Setup & Installation

**Prerequisites:** Python 3.10+ (and a GPU for significantly faster Demucs & Torchcrepe processing).

1. **Clone the repository:**
   ```bash
   git clone https://github.com/calvinbootsman/CalvinsKaraoke.git
   cd CalvinsKaraoke
   ```

2. **Install Dependencies:**
   Ensure you have PyTorch installed with CUDA support if you intend to use GPU acceleration. Then install the project requirements:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the Audio File Server:**
   The karaoke player needs a local CORS-enabled HTTP server to read the audio data for pitch extraction and playback. Open a separate terminal and run:
   ```bash
   python music/cors_server.py
   ```

4. **Run the Application:**
   ```bash
   streamlit run app.py
   ```

---

## 🕹️ Usage

* **Process a Song:** Paste a URL under the "Process New Song" tab and hit "Process". Processing runs asynchronously with progress bars so your UI remains responsive.
* **Saved Music:** View your catalog, check if processing was fully completed (All Stems & Pitch & Lyrics), or optionally hit the "Reprocess" button to catch missing stems without deleting the song.
* **Queue It Up:** Add songs, view the active Queue, or instantly play from the front.
* **Karaoke Window:** Interacting with the player in the main UI will automatically pop out the dedicated Karaoke window! Then just sing!

---

## 🛠️ Tech Stack
* **Frontend Controller:** Streamlit
* **Player UI:** Vanilla HTML/JS, embedded as an iframe, detached via Window Popup
* **Backend Utilities:** `yt-dlp`, `demucs`, `torchcrepe`, `syncedlyrics`
* **Local HTTP Server:** Python ThreadingHTTPServer

---

*Made with ❤️ for karaoke nights.*
