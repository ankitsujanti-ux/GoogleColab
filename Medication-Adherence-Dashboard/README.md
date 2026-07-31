# Medication Adherence – Agentic AI Dashboard

A modern, AI-driven dashboard for monitoring patient medication adherence with real-time analytics, risk assessment, and automated interventions.

## Features

- 📊 Real-time dashboard with animated KPIs and charts
- 🤖 AI-powered risk assessment and patient monitoring
- 📱 Automated patient notifications (SMS, Email, Pushover)
- 📈 Trend analysis and adherence distribution visualization
- 🔔 WebSocket-based real-time updates
- 🎨 Modern, responsive UI with smooth animations

## Tech Stack

- **Backend**: Flask + Flask-SocketIO (Python)
- **Frontend**: React.js with Plotly.js
- **AI**: OpenAI GPT models for intelligent risk assessment
- **Data**: Pandas for data processing

## Project Structure

```
.
├── main.py                 # Application entry point
├── app_flask.py            # Flask backend API
├── agent.py                # AI agent logic
├── advanced_adherence.py   # Advanced analytics
├── config.py               # Configuration
├── utils.py                # Utility functions
├── notifier.py             # Notification services
├── templates_helper.py      # Template utilities
├── requirements.txt        # Python dependencies
├── templates/              # HTML templates
├── frontend/               # React application
│   ├── src/               # React source code
│   ├── public/            # Static assets
│   └── package.json       # Node dependencies
└── README.md              # This file
```

## Setup

### Prerequisites

- Python 3.8+
- Node.js 16+
- npm or yarn

### Backend Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
Create a `.env` file in the project root:
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Or set environment variables:
```powershell
# Windows PowerShell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_MODEL="gpt-4o-mini"
```

3. **Sample / production data**: Place your patient Excel file at `Data/patients.xlsx` (or set `EXCEL_PATH` in `.env`). To generate a 500-row production-ready sample file:
```bash
python generate_patients_excel.py -n 500
```
Options: `-o path/to/file.xlsx`, `--seed 42`, `--no-backup`. See `python generate_patients_excel.py --help`.

### Frontend Setup

1. Install Node dependencies:
```bash
cd frontend
npm install
```

2. Build for production:
```bash
npm run build
```

## Running the Application

### Production Mode (Recommended)

1. Build the frontend:
```bash
cd frontend
npm run build
```

2. Start the Flask server:
```bash
python main.py
```

The application will be available at `http://localhost:5000`

### Development Mode

You need **two terminals**: the backend (Flask) and the frontend (React).

1. **Start the backend first (Terminal 1)** – this serves the API and notification preview:
```bash
python main.py
```
   Leave this running. You should see: `Backend API: http://localhost:5000`

2. **Start the frontend (Terminal 2)**:
```bash
cd frontend
npm start
```
   Frontend runs on `http://localhost:3000` and proxies API calls to the backend.

**Important:** `npm start` only starts the React app. The **notification preview** (Data Snapshot) and **chatbot** are served by the Python backend. After you change backend code (e.g. `agent.py`, `app_flask.py`, `pharmacy.py`), you must **restart the backend** (stop Terminal 1 with Ctrl+C, then run `python main.py` again). Restarting only the frontend will not load backend changes.

## Configuration

Key configuration options in `config.py`:
- `AUTO_REFRESH_SECONDS`: Dashboard refresh interval
- `THRESHOLD_LOW`: Low adherence threshold
- `THRESHOLD_MED`: Medium adherence threshold
- `OUTREACH_MAX_PER_DAY`: Maximum daily notifications
- `OUTREACH_COOLDOWN_DAYS`: Cooldown period between notifications

## API Endpoints

- `GET /api/health` - Health check
- `GET /api/dashboard-data` - Dashboard metrics and KPIs
- `GET /api/system-status` - System status information
- `GET /api/trend-chart` - Trend chart data
- `POST /api/system-control` - Control system settings

## WebSocket Events

- `notification_sent` - Fired when a notification is sent
- `high_risk_alert` - Fired when a high-risk patient is detected

## Notes

- If no OpenAI API key is present, the app runs in fallback mode (no crash)
- Patient data should be provided in the expected format (see `utils.py`)
- The dashboard automatically detects and processes high-risk patients
