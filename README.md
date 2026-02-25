# Fair Radiology Scheduling Engine

A deterministic, fair scheduling system for **weekday and weekend radiologist coverage** with vacation awareness, configurable policy controls, and QGenda integration capabilities.

This project provides a **data-driven scheduling engine** designed for hospital operations where fairness, auditability, and flexibility are critical for managing complex radiologist rotations across multiple sites and subspecialties.

## Key Features

- **Fair Distribution**: Long-term fairness using a modulo/round-robin cycle algorithm
- **Vacation Aware**: Handles vacations and exemptions without penalizing future assignments
- **Dual Scheduling**: Supports both weekday and weekend scheduling with unified engine
- **Back-to-Back Prevention**: Optional avoidance of consecutive weekend assignments
- **Deterministic**: Reproducible schedules with persistent cursor state
- **Multi-Pool Support**: Separate rotation pools for different shift types (Mercy, IR, Weekend)
- **QGenda Integration**: Pull schedules and push optimized assignments via REST API
- **Extensible**: Designed for FTE weighting, subspecialty matching, and GUI additions

###  Standalone Schedule Analyzer (No API Access Required!)

**Perfect for individual radiologists, schedulers, and staff without admin privileges:**

-  Analyze exported QGenda schedules for fairness
-  No API keys or admin access needed
-  Works completely offline with CSV/Excel exports
-  Generates detailed fairness reports and visualizations
-  Easy-to-use launcher scripts for Windows and Mac/Linux

**See**: `docs/END_USER_GUIDE.md` for complete instructions

## Table of Contents

- [How It Works](#how-it-works)
- [Two Usage Modes](#two-usage-modes)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [API Integration](#api-integration)
- [Documentation](#documentation)
- [Contributing](#contributing)

## Two Usage Modes

This project supports **two distinct modes** depending on your access level and needs:

### Mode 1: Standalone Analyzer (No API Access)  || RECOMMENDED FOR MOST USERS ||

**Perfect for**: Individual radiologists, schedulers, or anyone without QGenda admin/API access

**What you need**:
- Ability to export schedules from QGenda (standard user capability)
- Python installed on your computer
- No API keys or credentials required

**What it does**:
- Analyzes existing schedule exports for fairness
- Calculates detailed metrics (CV, standard deviation, workload balance)
- Generates visual charts and reports
- Identifies imbalances and outliers
- Works completely offline

**Quick Start**:
```bash
# Windows: Double-click run_analyzer.bat
# Mac/Linux: ./scripts/run_analyzer.sh

# Or command line:
python scripts/analyze_schedule.py schedule_export.xlsx
```

**Complete Guide**: See `docs/END_USER_GUIDE.md`

---

### Mode 2: Full Scheduling Engine (With API Access)

**Perfect for**: System administrators, schedulers with API access, automated scheduling

**What you need**:
- QGenda API key and company key
- Admin privileges
- Configuration files (roster, vacation maps)

**What it does**:
- Generates fair schedules from scratch using fairness algorithm
- Pulls data from QGenda via API
- Pushes optimized schedules back to QGenda
- Handles complex rotation rules and policies
- Maintains persistent cursor state for long-term fairness

**Quick Start**:
```bash
# Configure environment
cp .env.example .env
# Edit .env with API credentials

# Generate schedule
python scripts/generate_schedule.py
```

**Complete Guide**: See `docs/implementation_guide.md`

---

**Most users should start with Mode 1 (Standalone Analyzer)** to assess current fairness before implementing automated scheduling.

## 🔧 How It Works

### Core Algorithm

Radiologists are placed in a fixed ordered list, and assignments are drawn from an **infinite repeating stream**:

```
[A, B, C, D, …] → A → B → C → D → A → B → …
```

A global cursor walks the stream:
- Each assignment consumes one position
- Skipped (vacation) entries are **not consumed**, preserving fairness
- Deterministic output ensures reproducibility
- No duplicate assignments per scheduling period

### Scheduling Types

**Weekday Scheduling**
- Multiple shifts per day (e.g., M0, M1, M2, M3 for Mercy shifts)
- Each day scheduled independently
- Typically no back-to-back avoidance

**Weekend Scheduling**
- Multiple shifts per weekend (e.g., 6 shifts = 3 Saturday + 3 Sunday)
- Treated as single unit (Saturday date represents full weekend)
- Optional back-to-back weekend avoidance

**IR and Subspecialty Scheduling**
- Separate rotation pools for specialized coverage
- Independent cursors for different shift types

## 🔍 Prerequisites

### Required Software

- **Python**: 3.8 or higher
- **pip**: Latest version
- **Git**: For version control

### Required Python Packages

```
pandas>=1.3.0
openpyxl>=3.0.9
requests>=2.26.0
python-dateutil>=2.8.2
```

### Optional

- **QGenda Account**: For API integration
- **Excel**: For viewing/editing output files (or use Google Sheets/LibreOffice)

## 📥 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-organization/radiology-scheduler.git
cd radiology-scheduler
```

### 2. Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings
nano .env  # or use your preferred editor
```

## ⚙️ Configuration

### Required Configuration Files

#### 1. `roster_key.csv`

Define your radiologist roster with rotation pool membership:

```csv
id,index,initials,name,email,role,exempt_dates,fte,participates_mercy,participates_ir
1,0,TR,Ted Rothenberg,ted@hospital.org,Radiologist,"",1.0,yes,yes
2,1,SF,Sina Fartash,sina@hospital.org,Radiologist,"",1.0,yes,yes
3,2,SS,Sharjeel Sabir,sharjeel@hospital.org,Radiologist,"",1.0,yes,yes
```

**Important Rules:**
- `index` must be unique and contiguous (0 to N-1)
- Order defines rotation sequence
- Dates in `exempt_dates` must be `YYYY-MM-DD` format, semicolon-separated
- Weekend exemptions use the Saturday date

#### 2. `vacation_map.csv`

Track vacation/unavailability by date:

```csv
date,unavailable_staff
2025-06-23,John Johnson;Eric Chou
2025-06-24,Sina Fartash
```

#### 3. `.env` (Environment Variables)

```bash
# QGenda API Configuration
QGENDA_API_KEY=your_api_key_here
QGENDA_API_URL=https://api.qgenda.com/v2
QGENDA_COMPANY_KEY=your_company_key

# Scheduling Parameters
START_DATE=2026-01-01
END_DATE=2026-03-31
MERCY_SHIFTS_PER_DAY=4
IR_SHIFTS_PER_DAY=2
WEEKEND_SHIFTS_PER_WEEKEND=6

# Cursor State
WEEKDAY_CURSOR=0
WEEKEND_CURSOR=0
IR_CURSOR=0

# Policies
ALLOW_BACK_TO_BACK_WEEKENDS=false
ALLOW_FALLBACK_MODE=true
```

**Security Note**: Never commit your `.env` file to version control. The `.gitignore` is configured to exclude it.

## Usage

### Dry Run Mode (DEFAULT - No QGenda Push)

**Always use dry-run first.** Outputs to `outputs/` directory.

```bash
# Generate schedule for date range (never pushes to QGenda)
python scripts/run_dry_run.py --start 2026-03-01 --end 2026-06-30

# Or via module
python -m src.dry_run --start 2026-03-01 --end 2026-06-30
```

**Outputs:**
- `outputs/dry_run_*_schedule.csv` - Full schedule
- `outputs/dry_run_*_schedule.xlsx` - Excel grid
- `outputs/dry_run_*_fairness_report.txt` - CV%, top/bottom 3
- `outputs/dry_run_*_violations.txt` - Constraint violations

**Summary printed:** Total assignments, CV%, top/bottom 3 radiologists, violation counts.

### Basic Example

```python
from scheduling_engine import schedule_period
import pandas as pd

# Load roster and vacation data
people = load_roster('roster_key.csv')
vacation_map = load_vacation_map('vacation_map.csv')

# Get weekday dates (Monday-Friday)
weekday_dates = pd.date_range(start='2026-01-01', end='2026-03-31', freq='B')

# Schedule weekday Mercy shifts
mercy_schedule, cursor = schedule_period(
    people=people,
    dates=weekday_dates,
    shifts_per_period=4,        # M0, M1, M2, M3
    cursor=0,                    # Starting cursor position
    vacation_map=vacation_map,
    avoid_previous=False,        # No back-to-back avoidance for weekdays
)

# Export to Excel
export_to_excel(mercy_schedule, 'mercy_schedule.xlsx')
```

### Weekend Scheduling

```python
# Get weekend dates (Saturdays represent full weekend)
weekend_dates = pd.date_range(start='2026-01-01', end='2026-03-31', freq='W-SAT')

weekend_schedule, weekend_cursor = schedule_period(
    people=weekend_pool,
    dates=weekend_dates,
    shifts_per_period=6,         # Total shifts for Sat + Sun
    cursor=weekend_cursor,
    vacation_map=vacation_map,
    avoid_previous=True,         # Avoid back-to-back weekends
    allow_fallback=True,         # Allow violations if necessary
)
```

### QGenda Integration

```python
from qgenda_client import QGendaClient

# Initialize client
client = QGendaClient(api_key=QGENDA_API_KEY)

# Pull current schedule
current_schedule = client.get_schedule(
    start_date='2026-01-01',
    end_date='2026-03-31'
)

# Push optimized schedule
client.update_schedule(mercy_schedule)
```

## Project Structure

```
radiology-scheduler/
│
├── README.md                          # This file
├── LICENSE                            # License information
├── requirements.txt                   # Python dependencies
├── .gitignore                         # Git exclusions
├── .env.example                       # Example .env (Config., #3)
│
├── src/                               # Source code
│   ├── config.py                     # Roster, shift definitions, constraint weights
│   ├── engine.py                     # Weighted cursor scheduling (M0=0.25×, M1=1.0×)
│   ├── scheduling_engine.py          # Legacy scheduling algorithm
│   ├── qgenda_client.py              # QGenda API integration
│   ├── constraints.py                # Hard/soft constraint checking
│   ├── skills.py                     # Subspecialty matching
│   ├── dry_run.py                    # Dry-run mode (no QGenda push)
│   └── exporter.py                  # Excel/CSV export, fairness reports
│
├── config/                            # Configuration files
│   ├── roster_key.csv                # Radiologist roster
│   ├── vacation_map.csv              # Vacation tracking
│   └── cursor_state.json             # Persistent cursor positions
│
├── docs/                              # Documentation
│   ├── architecture.md               # Technical design and algorithms
│   ├── implementation_guide.md       # Step-by-step setup guide
│   ├── rotation_configuration.md     # Rotation pool definitions
│   ├── qgenda_integration.md         # QGenda API documentation
│   └── analysis/                      # Historical analysis reports
│       ├── comprehensive_analysis.md
│       ├── subspecialty_analysis.txt
│       └── fairness_analysis.md
│
├── data/                              # Historical and reference data
│   ├── qgenda_cleaned.csv            # Historical QGenda export
│   ├── scheduling_engine_configuration.xlsx
│   └── workload_comparison.csv
|
├── scripts/                           # Utility scripts
│   ├── generate_schedule.py          # Main schedule generation
│   ├── extract_vacations.py          # Extract vacations from QGenda
│   ├── validate_fairness.py          # Run fairness audits
│   └── deploy_to_qgenda.py          # Push schedules to QGenda
│
└── tests/                             # Unit and integration tests
    ├── test_scheduling_engine.py
    ├── test_qgenda_client.py
    └── test_fairness.py
```

## API Integration

### QGenda REST API

The system integrates with QGenda's REST API for:
- Pulling current schedule data
- Extracting vacation/time-off information
- Pushing optimized assignments
- Retrieving staff profiles

**API Endpoints Used:**
- `GET /v2/schedule` - Retrieve schedule data
- `POST /v2/schedule` - Create/update assignments
- `GET /v2/staff` - Get staff member details
- `GET /v2/timeoff` - Retrieve time-off requests

See `docs/qgenda_integration.md` for detailed API documentation.

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[Architecture](docs/architecture.md)**: Deep technical design, algorithms, and fairness guarantees
- **[Implementation Guide](docs/implementation_guide.md)**: Step-by-step setup and configuration
- **[Rotation Configuration](docs/rotation_configuration.md)**: Pool definitions and shift types
- **[QGenda Integration](docs/qgenda_integration.md)**: API usage and authentication

### Analysis Reports

Historical analysis and validation:
- **Comprehensive Scheduling Analysis**: Full fairness analysis with recommendations
- **Subspecialty Analysis**: Workload distribution across subspecialties
- **M0 Weighted Analysis**: Impact analysis of M0 shift weighting

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest tests/

# Run with coverage
python -m pytest --cov=src tests/

# Run specific test file
python -m pytest tests/test_scheduling_engine.py
```

## Monitoring and Auditing

### Generate Fairness Report

```bash
python scripts/validate_fairness.py --schedule mercy_schedule.xlsx --roster roster_key.csv
```

**Output includes:**
- Mean assignments per radiologist
- Standard deviation
- Coefficient of variation (CV)
- Per-person assignment counts
- Deviation from expected workload

**Goal**: CV < 10% indicates excellent fairness

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- QGenda for scheduling platform and API access
- SHIPMG Radiology group for requirements and validation
- Contributors to the fairness analysis and validation process

## Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Contact: juancarlosvera@gmail.com
- Documentation: See `docs/` directory

## Roadmap

Planned enhancements:
- [ ] FTE-weighted fairness calculations
- [ ] Separate Saturday/Sunday stream management
- [ ] Preference rules and soft constraints
- [ ] Web-based GUI for schedule visualization
- [ ] Calendar export (iCal, Google Calendar)
- [ ] Advanced metrics dashboard
- [ ] Multi-site support
- [ ] Mobile app for schedule viewing

---

**Version**: 1.0.0  
**Last Updated**: February 2026
