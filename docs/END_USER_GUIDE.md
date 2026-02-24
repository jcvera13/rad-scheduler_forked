# End-User Guide: Analyzing QGenda Schedules Without API Access

## 📖 Overview

This guide is for **radiologists, schedulers, and staff** who want to analyze schedule fairness but don't have QGenda API access or admin privileges.

**You only need**:
- Ability to export schedules from QGenda (standard user capability)
- Python installed on your computer
- This analyzer script

**No API keys, admin access, or programming knowledge required!**

---

## 🎯 What This Tool Does

The Fair Radiology Schedule Analyzer:

✅ Calculates fairness metrics (mean, standard deviation, coefficient of variation)  
✅ Identifies workload imbalances  
✅ Generates visual charts  
✅ Produces detailed reports  
✅ Works completely offline  

---

## 📥 Step 1: Export Your Schedule from QGenda

### Option A: Export from Web Interface (Most Common)

1. **Log in to QGenda** at your organization's URL

2. **Navigate to Schedule View**
   - Click on "Schedule" in the main menu
   - Select the appropriate schedule (e.g., "Radiology Call")

3. **Select Date Range**
   - Use the date picker to select your analysis period
   - Recommended: 3-6 months for meaningful analysis

4. **Export the Schedule**
   - Click the **"Export"** button (usually top right)
   - Select format:
     - **Excel (.xlsx)** - Recommended
     - CSV (.csv) - Also supported
   
5. **Save the File**
   - Save to your computer
   - Note the file location (e.g., `Downloads/schedule_export.xlsx`)

### Option B: Export from Reports

1. Go to **Reports** section in QGenda

2. Select **"Schedule Report"** or **"Staff Schedule"**

3. Configure report:
   - Date range: Your analysis period
   - Staff: All staff members (or specific group)
   - Include all shifts/tasks

4. **Generate and Download**
   - Click "Run Report"
   - Download as Excel or CSV

### What the Export Should Look Like

Your exported file should contain:

**Required columns** (at least one of these formats):

**Format 1: Row per assignment**
```
Date       | Staff Member    | Task Name  | Start Time | End Time
2026-01-15 | John Doe       | Mercy M0   | 07:00     | 17:00
2026-01-15 | Jane Smith     | Mercy M1   | 07:00     | 17:00
```

**Format 2: Staff in columns**
```
Date       | John Doe | Jane Smith | Bob Wilson | ...
2026-01-15 | M0       | M1         | M2         | ...
2026-01-16 | M1       | M2         | OFF        | ...
```

**Format 3: First/Last Name separate**
```
Date       | First Name | Last Name | Task Name
2026-01-15 | John       | Doe       | Mercy M0
2026-01-15 | Jane       | Smith     | Mercy M1
```

The analyzer can handle all these formats automatically!

---

## 🔧 Step 2: Install Python and Dependencies

### Check if Python is Already Installed

Open Terminal (Mac/Linux) or Command Prompt (Windows) and run:

```bash
python --version
```

If you see `Python 3.8` or higher, you're good! Skip to installing dependencies.

### Install Python (if needed)

**Windows:**
1. Download from [python.org](https://www.python.org/downloads/)
2. Run installer
3. ✅ **CHECK "Add Python to PATH"** during installation

**Mac:**
```bash
# Using Homebrew
brew install python3
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt-get install python3 python3-pip

# RedHat/CentOS
sudo yum install python3 python3-pip
```

### Install Required Libraries

```bash
# Install pandas (data processing)
pip install pandas

# Install openpyxl (Excel support)
pip install openpyxl

# Install matplotlib (charts - optional but recommended)
pip install matplotlib
```

Or install all at once:
```bash
pip install pandas openpyxl matplotlib
```

---

## 🚀 Step 3: Run the Analyzer

### Basic Usage

Navigate to where you saved the analyzer script:

```bash
cd /path/to/radiology-scheduler-project/scripts
```

Run the analyzer on your exported file:

```bash
python analyze_schedule.py /path/to/your/schedule_export.xlsx
```

### With Date Filtering

Analyze only a specific time period:

```bash
python analyze_schedule.py schedule_export.xlsx \
    --start-date 2026-01-01 \
    --end-date 2026-03-31
```

### Save Results to Specific Folder

```bash
python analyze_schedule.py schedule_export.xlsx --output-dir reports/Q1_2026
```

### Real Examples

**Example 1: Analyze full exported schedule**
```bash
python analyze_schedule.py ~/Downloads/radiology_schedule_2026.xlsx
```

**Example 2: Analyze specific quarter**
```bash
python analyze_schedule.py schedule.xlsx \
    --start-date 2026-01-01 \
    --end-date 2026-03-31 \
    --output-dir Q1_Analysis
```

**Example 3: Analyze CSV export**
```bash
python analyze_schedule.py schedule_export.csv
```

---

## 📊 Step 4: Understanding Your Results

### Console Output

The analyzer prints a summary directly to your screen:

```
📊 FAIRNESS ANALYSIS REPORT
================================================================================

📅 Date Range: 2026-01-01 to 2026-03-31
📆 Total Days: 90
👥 Staff Count: 15

📈 OVERALL FAIRNESS METRICS
   Mean assignments per person: 24.5
   Standard deviation: 2.3
   Coefficient of variation: 9.4%
   Min assignments: 21
   Max assignments: 28
   Range: 7

✅ Fairness Assessment: GOOD - Fair distribution

👤 PER-PERSON ASSIGNMENT COUNTS
Name                           Count  % of Mean   Deviation
--------------------------------------------------------------------------------
Alice Brown                       28      114.3%      +3.5
Charles Doe                       27      110.2%      +2.5
Emily Foster                      26      106.1%      +1.5
...
```

### Generated Files

The analyzer creates these files in your output directory:

#### 1. `fairness_report.txt`

Detailed text report with:
- Overall statistics
- Per-person breakdown
- Assessment and recommendations

**Open with**: Any text editor (Notepad, TextEdit, VS Code)

#### 2. `fairness_data.json`

Machine-readable data in JSON format for further analysis

**Use for**: Importing into Excel, custom analysis, tracking over time

#### 3. `assignment_distribution.png`

Bar chart showing assignments per person:
- Blue bars: Within normal range
- Red bars: Significantly above average
- Dark blue bars: Significantly below average
- Red dashed line: Mean assignments

#### 4. `deviation_from_mean.png`

Shows how far each person deviates from the average:
- Positive (red): More assignments than average
- Negative (blue): Fewer assignments than average

#### 5. `assignment_timeline.png`

Timeline showing when each person was assigned (top 15 staff)

---

## 📐 Interpreting Fairness Metrics

### Coefficient of Variation (CV)

This is the **primary fairness metric**:

| CV Range | Assessment | Meaning |
|----------|------------|---------|
| < 5% | 🌟 **EXCELLENT** | Near perfect fairness |
| 5-10% | ✅ **GOOD** | Fair distribution, minor variations |
| 10-20% | ⚠️ **MODERATE** | Some imbalance, should review |
| > 20% | ❌ **POOR** | Significant imbalance, needs attention |

**Example**: CV of 9.4% means the standard deviation is 9.4% of the mean. This indicates good fairness with small variations.

### Standard Deviation

Shows the typical variation from the mean:
- **Low** (< 3): Very consistent assignments
- **Medium** (3-5): Some variation, generally acceptable
- **High** (> 5): Wide disparities between staff

### Range (Max - Min)

The difference between highest and lowest assignments:
- **< 5**: Excellent balance
- **5-10**: Good balance  
- **10-20**: Moderate imbalance
- **> 20**: Significant imbalance

---

## 🔍 Common Scenarios and Interpretations

### Scenario 1: Good Fairness (CV < 10%)

**Your results show**:
- CV: 8.2%
- Most people within ±2 assignments of mean
- Small range between max and min

**What this means**:
- ✅ Schedule is fair
- ✅ Workload distributed evenly
- ✅ Current scheduling approach is working

**Action**: Continue current practices, monitor quarterly

---

### Scenario 2: Moderate Imbalance (CV 10-20%)

**Your results show**:
- CV: 15.3%
- Some people have 20+ assignments, others have 10-15
- Larger gaps between staff

**What this means**:
- ⚠️ Some imbalance exists
- ⚠️ Certain staff may be over/under-utilized
- ⚠️ May be due to vacations, availability, or scheduling bias

**Action**: 
- Review outliers (highest/lowest)
- Check if due to legitimate reasons (part-time, vacations)
- Consider implementing fairer rotation algorithm

---

### Scenario 3: Significant Imbalance (CV > 20%)

**Your results show**:
- CV: 25.8%
- Wide disparities: some have 30+ assignments, others have 10-15
- Large range (20+ difference)

**What this means**:
- ❌ Significant unfairness in distribution
- ❌ Some staff significantly overworked, others underutilized
- ❌ Current scheduling approach needs revision

**Action**:
- **Immediate**: Review and adjust upcoming schedules
- **Short-term**: Implement fairer rotation algorithm
- **Long-term**: Consider using the full scheduling engine with rotation rules

---

## 🛠️ Troubleshooting

### Problem: "File not found" error

**Cause**: Wrong file path

**Solution**:
```bash
# Check your file location
ls ~/Downloads/

# Use full path
python analyze_schedule.py /Users/yourname/Downloads/schedule.xlsx
```

---

### Problem: "No assignments found in data"

**Cause**: Unexpected file format

**Solution**:
1. Open the Excel/CSV file and check structure
2. Ensure it has:
   - Date column
   - Staff names (in columns or rows)
   - Assignment data

3. If format is unusual, try exporting differently from QGenda

---

### Problem: "Module not found" error

**Cause**: Missing Python libraries

**Solution**:
```bash
# Install missing libraries
pip install pandas openpyxl matplotlib

# Or if using Python 3 explicitly
pip3 install pandas openpyxl matplotlib
```

---

### Problem: Charts not generating

**Cause**: Matplotlib not installed

**Solution**:
```bash
pip install matplotlib
```

**Or**: Analysis still works, just without visualizations

---

### Problem: Permission denied

**Cause**: Output directory doesn't exist or no write permission

**Solution**:
```bash
# Create output directory first
mkdir my_reports

# Then run with that directory
python analyze_schedule.py schedule.xlsx --output-dir my_reports
```

---

## 🎓 Tips for Best Results

### 1. Choose Appropriate Time Period

- **Too short** (< 1 month): Noise from individual weeks may skew results
- **Too long** (> 6 months): May include staffing changes, policy shifts
- **Recommended**: 3-6 months for meaningful analysis

### 2. Exclude Transition Periods

Avoid periods with:
- Major staff changes (new hires, departures)
- Policy changes
- Unusual events (pandemic, disasters)

### 3. Regular Monitoring

Run analysis:
- **Quarterly**: Check fairness every 3 months
- **Before/After**: When changing scheduling approach
- **When Concerned**: If staff raise fairness concerns

### 4. Compare Over Time

Save each analysis with date in folder name:
```bash
python analyze_schedule.py schedule.xlsx --output-dir Analysis_2026_Q1
python analyze_schedule.py schedule.xlsx --output-dir Analysis_2026_Q2
```

This lets you track if fairness is improving or declining.

---

## 📋 Quick Reference Card

### Basic Command
```bash
python analyze_schedule.py your_schedule.xlsx
```

### With Options
```bash
python analyze_schedule.py your_schedule.xlsx \
    --start-date 2026-01-01 \
    --end-date 2026-03-31 \
    --output-dir results/
```

### Output Files
- `fairness_report.txt` - Detailed text report
- `fairness_data.json` - Machine-readable data
- `assignment_distribution.png` - Bar chart
- `deviation_from_mean.png` - Deviation chart
- `assignment_timeline.png` - Timeline view

### Fairness Benchmarks
- **CV < 10%** = Good fairness ✅
- **CV 10-20%** = Moderate imbalance ⚠️
- **CV > 20%** = Significant imbalance ❌

---

## 🤝 Getting Help

If you encounter issues:

1. **Check this guide** for troubleshooting section
2. **Verify file format** - open Excel/CSV and check structure
3. **Try simple test**:
   ```bash
   python analyze_schedule.py --help
   ```
4. **Contact Devloper (jcvera)** for Python installation issues
5. **Ask your scheduler** for help exporting from QGenda

---

## 🎯 Next Steps

After running your first analysis:

1. **Review results** - understand your baseline fairness
2. **Share with team** - discuss findings with colleagues
3. **Track over time** - run quarterly to monitor trends
4. **Take action** - if fairness is poor, consider using the full scheduling engine

---

## 📚 Additional Resources

- **Full Documentation**: See `docs/` folder for technical details
- **Scheduling Engine**: For automated fair scheduling with rules
- **QGenda Guide**: See `docs/qgenda_integration.md` for API access

---

**Last Updated**: February 2026  
**Version**: 1.0  
**Support**: See repository README for contact information
