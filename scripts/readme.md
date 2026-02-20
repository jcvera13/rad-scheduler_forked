# Scripts Directory

This directory contains utility scripts for analyzing QGenda schedule exports and generating fair schedules.

## 📋 Available Scripts

### 1. `analyze_schedule.py` - **STANDALONE SCHEDULE ANALYZER** ⭐

**Purpose**: Analyze exported QGenda schedules for fairness without needing API access.

**Who it's for**: Anyone who can export schedules from QGenda (no admin/API access needed)

**What it does**:
- Calculates fairness metrics (CV, standard deviation, mean)
- Generates visual charts
- Creates detailed reports
- Identifies workload imbalances

**Requirements**:
- Python 3.8+
- pandas
- openpyxl (for Excel files)
- matplotlib (for visualizations)

**Usage**:

```bash
# Basic usage
python analyze_schedule.py schedule_export.xlsx

# With date filtering
python analyze_schedule.py schedule_export.xlsx \
    --start-date 2026-01-01 \
    --end-date 2026-03-31

# Save to specific directory
python analyze_schedule.py schedule_export.xlsx --output-dir reports/Q1
```

**Input**: QGenda schedule export (Excel or CSV)

**Output**:
- `fairness_report.txt` - Detailed text report
- `fairness_data.json` - Machine-readable data
- `assignment_distribution.png` - Bar chart
- `deviation_from_mean.png` - Deviation chart
- `assignment_timeline.png` - Timeline visualization

**See**: `docs/END_USER_GUIDE.md` for complete instructions

---

### 2. `run_analyzer.bat` - **Windows Launcher** (Windows only)

**Purpose**: Easy-to-use launcher for Windows users

**Usage**:
1. Double-click `run_analyzer.bat`
2. Follow the interactive prompts
3. Results automatically saved with timestamp

**Features**:
- Checks Python installation
- Installs missing packages automatically
- Interactive file selection
- Optional date filtering
- Automatic folder creation
- Opens results folder when done

**Perfect for**: Non-technical users on Windows

---

### 3. `run_analyzer.sh` - **Mac/Linux Launcher** (Mac/Linux only)

**Purpose**: Easy-to-use launcher for Mac and Linux users

**Usage**:
```bash
# First time: Make executable
chmod +x run_analyzer.sh

# Run
./run_analyzer.sh
```

**Features**:
- Checks Python 3 installation
- Installs missing packages automatically
- Interactive file selection
- Optional date filtering
- Automatic folder creation
- Opens results folder when done

**Perfect for**: Non-technical users on Mac/Linux

---

## 🚀 Quick Start for End Users

### Windows Users

1. Download the project
2. Navigate to `scripts/` folder
3. Double-click `run_analyzer.bat`
4. Follow prompts

### Mac/Linux Users

1. Download the project
2. Open Terminal
3. Navigate to scripts folder:
   ```bash
   cd /path/to/radiology-scheduler-project/scripts
   ```
4. Make executable (first time only):
   ```bash
   chmod +x run_analyzer.sh
   ```
5. Run:
   ```bash
   ./run_analyzer.sh
   ```

---

## 📊 Understanding Your Analysis Results

### Fairness Metrics

**Coefficient of Variation (CV)** - Primary metric:
- **< 5%**: 🌟 Excellent fairness
- **5-10%**: ✅ Good fairness
- **10-20%**: ⚠️ Moderate imbalance
- **> 20%**: ❌ Significant imbalance

**Standard Deviation** - Typical variation:
- **< 3**: Very consistent
- **3-5**: Some variation (acceptable)
- **> 5**: Wide disparities

**Range** - Difference between highest and lowest:
- **< 5**: Excellent balance
- **5-10**: Good balance
- **> 10**: Significant imbalance

### Generated Charts

1. **assignment_distribution.png**
   - Bar chart showing assignments per person
   - Red line shows the mean
   - Dark red bars = significantly above average
   - Dark blue bars = significantly below average

2. **deviation_from_mean.png**
   - Shows how far each person deviates from average
   - Red = more than average
   - Blue = less than average

3. **assignment_timeline.png**
   - Timeline showing when people were assigned
   - Helps identify clustering or gaps

---

## 💡 Common Use Cases

### Use Case 1: Quarterly Fairness Review

Run every 3 months to track fairness over time:

```bash
# Q1 Analysis
python analyze_schedule.py schedule.xlsx \
    --start-date 2026-01-01 \
    --end-date 2026-03-31 \
    --output-dir Analysis_Q1_2026

# Q2 Analysis
python analyze_schedule.py schedule.xlsx \
    --start-date 2026-04-01 \
    --end-date 2026-06-30 \
    --output-dir Analysis_Q2_2026
```

Compare CV across quarters to see if fairness is improving.

---

### Use Case 2: Before/After Comparison

Test if new scheduling approach improved fairness:

```bash
# Before new system
python analyze_schedule.py old_schedule.xlsx \
    --output-dir Before_New_System

# After new system
python analyze_schedule.py new_schedule.xlsx \
    --output-dir After_New_System
```

Compare the CV values to measure improvement.

---

### Use Case 3: Responding to Fairness Concerns

When staff raise concerns about fairness:

```bash
# Analyze recent period
python analyze_schedule.py schedule.xlsx \
    --start-date 2026-02-01 \
    --end-date 2026-02-16 \
    --output-dir Fairness_Investigation
```

Use the detailed per-person breakdown to identify issues.

---

## 🔧 Troubleshooting

### "python: command not found"

**Solution**: Install Python from [python.org](https://www.python.org/downloads/)

For Windows: Make sure to check "Add Python to PATH" during installation

---

### "No module named 'pandas'"

**Solution**: Install required packages:
```bash
pip install pandas openpyxl matplotlib
```

---

### "No assignments found in data"

**Cause**: Unexpected file format

**Solution**:
1. Open your Excel/CSV file
2. Verify it contains:
   - Date column
   - Staff names (as columns or in rows)
   - Assignment data
3. See `docs/END_USER_GUIDE.md` for expected formats

---

### "Permission denied" (Mac/Linux)

**Solution**: Make script executable:
```bash
chmod +x run_analyzer.sh
# or
chmod +x analyze_schedule.py
```

---

## 📚 Additional Documentation

- **End User Guide**: `docs/END_USER_GUIDE.md` - Complete guide for non-technical users
- **Implementation Guide**: `docs/implementation_guide.md` - For setting up full scheduling engine
- **Architecture**: `docs/architecture.md` - Technical details on fairness algorithm

---

## 🆘 Getting Help

1. **Read the guides**:
   - `END_USER_GUIDE.md` for usage instructions
   - Troubleshooting sections in this README

2. **Check file format**:
   - Open your export in Excel/CSV viewer
   - Verify structure matches expected formats

3. **Test with simple command**:
   ```bash
   python analyze_schedule.py --help
   ```

4. **Contact support**: See main README.md for contact information

---

## 🎯 Future Scripts (Coming Soon)

These scripts are planned but not yet implemented:

- `generate_schedule.py` - Generate fair schedules using the engine
- `extract_vacations.py` - Extract vacation data from QGenda exports
- `validate_fairness.py` - Validate proposed schedules before publishing
- `deploy_to_qgenda.py` - Push schedules to QGenda (requires API access)
- `compare_schedules.py` - Compare fairness between different time periods

Want to contribute? See `CONTRIBUTING.md`!

---

## 📄 Script Files Summary

| File | Purpose | User Type | Platform |
|------|---------|-----------|----------|
| `analyze_schedule.py` | Main analyzer | All | All |
| `run_analyzer.bat` | Windows launcher | Non-technical | Windows |
| `run_analyzer.sh` | Mac/Linux launcher | Non-technical | Mac/Linux |

---

**Version**: 1.0  
**Last Updated**: February 2026  
**For**: Fair Radiology Scheduling Engine
