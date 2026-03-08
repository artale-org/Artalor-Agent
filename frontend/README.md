# Artalor Frontend

## 🌟 Overview

This is the frontend for the Artalor AI Video Creation Platform. It provides a modern, responsive web interface for creating professional advertisement and story videos. The frontend is served directly by the Flask backend — no separate web server is needed.

## ✨ Key Features

-   **Animated Home Page**: A visually engaging home page with a particle animation background.
-   **Dual Workflow Support**: Switch between **Ads Video** and **Story Video** creation modes.
-   **Asynchronous Generation**: Click "Generate" and get redirected to the results page immediately while the backend processes in the background.
-   **Real-Time Results Gallery**: Assets (images, videos, audio) appear as they are generated. Watch your video come to life in real-time.
-   **Interactive Editor**: Click any asset to view contextual info in the Text Preview panel. Edit text inline and regenerate individual assets.
-   **Fine-Grained Regeneration**: Edit and regenerate individual audio segments, video clips, images, or background music without re-running the entire workflow.
-   **Workflow Controls**: Stop, continue, and rerun workflows on demand from the results page.
-   **API Keys Management**: Configure your own OpenAI and Replicate API keys via the **API Keys** button in the navigation bar. Keys are stored locally in your browser and sent per-request.

## 📖 How to Use

The backend server serves the frontend directly — no separate setup is needed.

### 1. Start the Backend Server

```bash
python backend/server.py
```

### 2. Access the Application

Open your web browser and navigate to:

[http://localhost:5001](http://localhost:5001)

### 3. Configure API Keys

Click the **API Keys** button in the top navigation bar to enter your OpenAI and Replicate API keys. These are stored in your browser's local storage and sent securely to the server only during generation.

> You can also set API keys via a `.env` file in the `backend/` directory. See the backend README for details.

### 4. Create Your Video

-   **Ads Video**: Enter a product description, upload a product image, and click **Generate**.
-   **Story Video**: Write or paste a story, optionally upload a character image, and click **Generate**.

### 5. View & Edit Results

-   You will be automatically redirected to the results page.
-   Assets appear in real-time as they are generated.
-   Click any asset to see its details in the Text Preview panel.
-   Edit text inline and click **Regenerate** to update individual assets.

## 📁 Frontend File Structure

-   `index.html`: Main landing page with workflow selection and generation forms.
-   `results.html`: Results/editor page for viewing and editing generated assets.
-   `style.css`: Main stylesheet for both pages (dark theme, responsive grid, animations).
-   `auth.css`: Styles for the navigation bar, API Keys modal, and related UI elements.
-   `script.js`: JavaScript for the home page — form submission, model loading, project listing.
-   `results.js`: JavaScript for the results page — real-time polling, asset display, text preview, regeneration, workflow controls.
-   `auth.js`: API Keys Manager — handles local storage of API keys and the API Keys modal.
-   `app.js`: Configuration for the `particles.js` animation on the home page.
