#!/bin/bash

# Fair Radiology Schedule Analyzer - Mac/Linux Launcher
# Run this script to analyze your schedule

echo "========================================"
echo "Fair Radiology Schedule Analyzer"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo ""
    echo "Installation instructions:"
    echo "  Mac: brew install python3"
    echo "  Ubuntu/Debian: sudo apt-get install python3 python3-pip"
    echo "  RedHat/CentOS: sudo yum install python3 python3-pip"
    echo ""
    exit 1
fi

echo "✓ Python found: $(python3 --version)"
echo ""

# Check for required packages
echo "Checking required packages..."

check_and_install() {
    package=$1
    python3 -c "import $package" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "Installing $package..."
        pip3 install "$package"
    else
        echo "✓ $package installed"
    fi
}

check_and_install pandas
check_and_install openpyxl
check_and_install matplotlib

echo ""
echo "========================================"
echo "Ready to analyze!"
echo "========================================"
echo ""

# Prompt for file path
read -p "Enter path to your schedule file: " schedule_file

# Expand ~ to home directory
schedule_file="${schedule_file/#\~/$HOME}"

# Remove quotes if present
schedule_file="${schedule_file//\"/}"

# Check if file exists
if [ ! -f "$schedule_file" ]; then
    echo ""
    echo "ERROR: File not found: $schedule_file"
    echo ""
    exit 1
fi

echo ""
echo "Analyzing: $schedule_file"
echo ""

# Ask if user wants to filter by date
read -p "Filter by date range? (y/n): " use_dates

if [[ $use_dates =~ ^[Yy]$ ]]; then
    read -p "Enter start date (YYYY-MM-DD): " start_date
    read -p "Enter end date (YYYY-MM-DD): " end_date
    
    # Create output directory with timestamp
    output_dir="Analysis_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$output_dir"
    
    python3 analyze_schedule.py "$schedule_file" \
        --start-date "$start_date" \
        --end-date "$end_date" \
        --output-dir "$output_dir"
else
    # Create output directory with timestamp
    output_dir="Analysis_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$output_dir"
    
    python3 analyze_schedule.py "$schedule_file" --output-dir "$output_dir"
fi

echo ""
echo "========================================"
echo "Analysis Complete!"
echo "========================================"
echo ""
echo "Results saved to: $output_dir"
echo ""
echo "Files generated:"
echo "  - fairness_report.txt (detailed report)"
echo "  - fairness_data.json (data file)"
echo "  - assignment_distribution.png (chart)"
echo "  - deviation_from_mean.png (chart)"
echo "  - assignment_timeline.png (timeline)"
echo ""

# Ask if user wants to open results folder
read -p "Open results folder? (y/n): " open_folder
if [[ $open_folder =~ ^[Yy]$ ]]; then
    # Try different commands based on OS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        open "$output_dir"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v xdg-open &> /dev/null; then
            xdg-open "$output_dir"
        elif command -v gnome-open &> /dev/null; then
            gnome-open "$output_dir"
        else
            echo "Results folder: $output_dir"
        fi
    fi
fi

echo ""
echo "Done! Press Enter to exit..."
read
