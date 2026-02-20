"""
Fair Radiology Scheduling Engine
Core scheduling algorithm implementation

This module implements the deterministic, fair scheduling algorithm
described in docs/architecture.md
"""

from typing import List, Dict, Set, Optional, Tuple
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)


class SchedulingEngine:
    """
    Core scheduling engine using modulo/round-robin fairness algorithm
    """
    
    def __init__(self, people: List[Dict], cursor: int = 0):
        """
        Initialize the scheduling engine
        
        Args:
            people: List of radiologist dictionaries with 'name', 'index', etc.
            cursor: Starting cursor position in the infinite stream
        """
        self.people = people
        self.cursor = cursor
        self.name_list = [p['name'] for p in people]
        self.N = len(people)
        
        # Validate indices are contiguous
        indices = sorted([p['index'] for p in people])
        if indices != list(range(self.N)):
            raise ValueError("Radiologist indices must be contiguous from 0 to N-1")
    
    def schedule_period(
        self,
        dates: List[date],
        shifts_per_period: int,
        vacation_map: Optional[Dict[str, List[str]]] = None,
        avoid_previous: bool = False,
        allow_fallback: bool = True
    ) -> Tuple[Dict[str, List[str]], int]:
        """
        Schedule shifts for a date range
        
        Args:
            dates: List of dates to schedule
            shifts_per_period: Number of shifts per date (or weekend)
            vacation_map: Dict mapping date strings to list of unavailable staff
            avoid_previous: If True, avoid assigning same people as previous period
            allow_fallback: If True, relax back-to-back rule when necessary
            
        Returns:
            Tuple of (schedule dict, final cursor position)
            Schedule dict maps date strings to list of assigned staff names
        """
        if vacation_map is None:
            vacation_map = {}
        
        schedule = {}
        stream_pos = self.cursor
        last_assigned = set()
        
        for d in dates:
            key = d.strftime("%Y-%m-%d")
            
            # Get unavailable staff for this date
            unavailable = set(vacation_map.get(key, []))
            
            # Add back-to-back avoidance if enabled
            if avoid_previous and last_assigned:
                unavailable |= last_assigned
            
            assigned = []
            
            # Assign each shift for this period
            for shift_num in range(shifts_per_period):
                probe = stream_pos
                tries = 0
                chosen = None
                max_tries = self.N * 2
                
                # Probe the stream for available person
                while tries < max_tries:
                    candidate = self.name_list[probe % self.N]
                    
                    # Check if candidate is available and not already assigned
                    if candidate not in unavailable and candidate not in assigned:
                        chosen = candidate
                        stream_pos = probe + 1
                        assigned.append(candidate)
                        logger.debug(f"Assigned {candidate} to {key} shift {shift_num}")
                        break
                    
                    probe += 1
                    tries += 1
                
                # Handle case where no one available
                if chosen is None:
                    if allow_fallback and avoid_previous:
                        # Retry without back-to-back restriction
                        logger.warning(f"Insufficient staff for {key} shift {shift_num}, "
                                     f"relaxing back-to-back rule")
                        unavailable -= last_assigned
                        
                        # Try again
                        probe = stream_pos
                        tries = 0
                        while tries < max_tries:
                            candidate = self.name_list[probe % self.N]
                            if candidate not in unavailable and candidate not in assigned:
                                chosen = candidate
                                stream_pos = probe + 1
                                assigned.append(candidate)
                                logger.debug(f"Assigned {candidate} to {key} shift {shift_num} "
                                           f"(fallback mode)")
                                break
                            probe += 1
                            tries += 1
                    
                    if chosen is None:
                        raise RuntimeError(
                            f"Insufficient staff available for {key} shift {shift_num}. "
                            f"Unavailable: {unavailable}, Already assigned: {assigned}"
                        )
            
            last_assigned = set(assigned)
            schedule[key] = assigned
            
            logger.info(f"Scheduled {key}: {assigned}")
        
        return schedule, stream_pos
    
    def get_cursor(self) -> int:
        """Get current cursor position"""
        return self.cursor
    
    def set_cursor(self, cursor: int):
        """Set cursor position"""
        self.cursor = cursor


def load_roster(roster_file: str) -> List[Dict]:
    """
    Load radiologist roster from CSV file
    
    Args:
        roster_file: Path to roster_key.csv
        
    Returns:
        List of radiologist dictionaries
    """
    import pandas as pd
    
    df = pd.read_csv(roster_file)
    
    # Convert to list of dicts
    people = []
    for _, row in df.iterrows():
        person = {
            'id': row['id'],
            'index': int(row['index']),
            'initials': row['initials'],
            'name': row['name'],
            'email': row.get('email', ''),
            'role': row.get('role', 'Radiologist'),
            'fte': float(row.get('fte', 1.0)),
        }
        
        # Parse exempt dates
        if 'exempt_dates' in row and pd.notna(row['exempt_dates']) and row['exempt_dates']:
            person['exempt_dates'] = row['exempt_dates'].split(';')
        else:
            person['exempt_dates'] = []
        
        people.append(person)
    
    return people


def load_vacation_map(vacation_file: str) -> Dict[str, List[str]]:
    """
    Load vacation map from CSV file
    
    Args:
        vacation_file: Path to vacation_map.csv
        
    Returns:
        Dictionary mapping date strings to list of unavailable staff
    """
    import pandas as pd
    
    df = pd.read_csv(vacation_file)
    
    vacation_map = {}
    for _, row in df.iterrows():
        date_str = row['date']
        if pd.notna(row['unavailable_staff']) and row['unavailable_staff']:
            staff_list = row['unavailable_staff'].split(';')
            vacation_map[date_str] = staff_list
        else:
            vacation_map[date_str] = []
    
    return vacation_map


def calculate_fairness_metrics(schedule: Dict[str, List[str]], people: List[Dict]) -> Dict:
    """
    Calculate fairness metrics for a schedule
    
    Args:
        schedule: Schedule dictionary
        people: List of radiologist dictionaries
        
    Returns:
        Dictionary with fairness metrics
    """
    import numpy as np
    
    # Count assignments per person
    counts = {p['name']: 0 for p in people}
    
    for date, assignments in schedule.items():
        for person in assignments:
            if person in counts:
                counts[person] += 1
    
    values = list(counts.values())
    mean = np.mean(values)
    std = np.std(values)
    cv = (std / mean * 100) if mean > 0 else 0
    
    return {
        'mean': mean,
        'std': std,
        'cv': cv,
        'min': min(values),
        'max': max(values),
        'counts': counts
    }


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    print("Fair Radiology Scheduling Engine")
    print("See docs/architecture.md for detailed documentation")
    print("\nExample usage:")
    print("  from scheduling_engine import SchedulingEngine, load_roster")
    print("  people = load_roster('config/roster_key.csv')")
    print("  engine = SchedulingEngine(people, cursor=0)")
    print("  schedule, cursor = engine.schedule_period(dates, shifts_per_period=4)")
