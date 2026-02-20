"""
QGenda API Client
Handles authentication and API calls to QGenda REST API

Documentation: https://restapi.qgenda.com/
"""

import requests
import logging
from typing import Dict, List, Optional
from datetime import datetime, date
import time

logger = logging.getLogger(__name__)


class QGendaClient:
    """
    Client for interacting with QGenda REST API
    """
    
    def __init__(
        self,
        api_key: str,
        company_key: str,
        base_url: str = "https://api.qgenda.com/v2"
    ):
        """
        Initialize QGenda client
        
        Args:
            api_key: QGenda API key
            company_key: QGenda company key
            base_url: Base URL for QGenda API
        """
        self.api_key = api_key
        self.company_key = company_key
        self.base_url = base_url.rstrip('/')
        
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })
    
    def get_schedule(
        self,
        start_date: str,
        end_date: str,
        include_open_shifts: bool = False
    ) -> List[Dict]:
        """
        Retrieve schedule data from QGenda
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            include_open_shifts: Include unassigned shifts
            
        Returns:
            List of schedule entries
        """
        endpoint = f"{self.base_url}/schedule"
        
        params = {
            'companyKey': self.company_key,
            'startDate': start_date,
            'endDate': end_date,
            'includeOpenShifts': include_open_shifts
        }
        
        logger.info(f"Fetching schedule from {start_date} to {end_date}")
        
        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Retrieved {len(data)} schedule entries")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching schedule: {e}")
            raise
    
    def get_staff(self) -> List[Dict]:
        """
        Retrieve staff member list
        
        Returns:
            List of staff member details
        """
        endpoint = f"{self.base_url}/staff"
        
        params = {
            'companyKey': self.company_key
        }
        
        logger.info("Fetching staff list")
        
        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Retrieved {len(data)} staff members")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching staff: {e}")
            raise
    
    def get_time_off(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """
        Retrieve time-off/vacation requests
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            List of time-off entries
        """
        endpoint = f"{self.base_url}/timeoff"
        
        params = {
            'companyKey': self.company_key,
            'startDate': start_date,
            'endDate': end_date
        }
        
        logger.info(f"Fetching time-off from {start_date} to {end_date}")
        
        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Retrieved {len(data)} time-off entries")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching time-off: {e}")
            raise
    
    def create_schedule_entry(
        self,
        staff_key: str,
        task_key: str,
        date: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict:
        """
        Create a single schedule entry
        
        Args:
            staff_key: Staff member key/ID
            task_key: Task/shift key/ID
            date: Date (YYYY-MM-DD)
            start_time: Start time (HH:MM)
            end_time: End time (HH:MM)
            
        Returns:
            Created schedule entry
        """
        endpoint = f"{self.base_url}/schedule"
        
        payload = {
            'CompanyKey': self.company_key,
            'StaffKey': staff_key,
            'TaskKey': task_key,
            'Date': date
        }
        
        if start_time:
            payload['StartTime'] = start_time
        if end_time:
            payload['EndTime'] = end_time
        
        logger.info(f"Creating schedule entry: {staff_key} -> {task_key} on {date}")
        
        try:
            response = self.session.post(endpoint, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Created schedule entry successfully")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating schedule entry: {e}")
            raise
    
    def update_schedule(
        self,
        schedule: Dict[str, List[str]],
        task_mapping: Dict[str, str],
        staff_mapping: Dict[str, str],
        rate_limit_delay: float = 0.5
    ) -> List[Dict]:
        """
        Batch update schedule entries
        
        Args:
            schedule: Schedule dict from scheduling engine
            task_mapping: Map shift names to QGenda task keys
            staff_mapping: Map staff names to QGenda staff keys
            rate_limit_delay: Delay between requests (seconds)
            
        Returns:
            List of created entries
        """
        results = []
        total = sum(len(assignments) for assignments in schedule.values())
        count = 0
        
        logger.info(f"Uploading {total} schedule entries to QGenda")
        
        for date_str, assignments in schedule.items():
            for shift_num, person_name in enumerate(assignments):
                count += 1
                
                # Get QGenda keys
                staff_key = staff_mapping.get(person_name)
                # Assume shift naming convention like "Mercy 0", "Mercy 1"
                task_key = task_mapping.get(f"Mercy {shift_num}")
                
                if not staff_key or not task_key:
                    logger.warning(
                        f"Skipping {person_name} on {date_str}: "
                        f"missing staff_key={staff_key} or task_key={task_key}"
                    )
                    continue
                
                try:
                    result = self.create_schedule_entry(
                        staff_key=staff_key,
                        task_key=task_key,
                        date=date_str
                    )
                    results.append(result)
                    
                    logger.info(f"Progress: {count}/{total}")
                    
                    # Rate limiting
                    time.sleep(rate_limit_delay)
                    
                except Exception as e:
                    logger.error(f"Failed to upload {person_name} on {date_str}: {e}")
        
        logger.info(f"Successfully uploaded {len(results)}/{total} entries")
        return results
    
    def delete_schedule_entry(self, schedule_key: str) -> bool:
        """
        Delete a schedule entry
        
        Args:
            schedule_key: QGenda schedule entry key
            
        Returns:
            True if successful
        """
        endpoint = f"{self.base_url}/schedule/{schedule_key}"
        
        params = {
            'companyKey': self.company_key
        }
        
        logger.info(f"Deleting schedule entry {schedule_key}")
        
        try:
            response = self.session.delete(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            logger.info("Deleted schedule entry successfully")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error deleting schedule entry: {e}")
            return False


def extract_vacation_data(client: QGendaClient, start_date: str, end_date: str) -> Dict[str, List[str]]:
    """
    Extract vacation data from QGenda and convert to vacation_map format
    
    Args:
        client: QGendaClient instance
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        
    Returns:
        Dictionary mapping dates to list of unavailable staff
    """
    time_off = client.get_time_off(start_date, end_date)
    
    vacation_map = {}
    
    for entry in time_off:
        # Extract staff name and date
        # Adjust field names based on actual QGenda API response
        staff_name = f"{entry.get('FirstName', '')} {entry.get('LastName', '')}"
        date_str = entry.get('Date', '')
        
        if date_str not in vacation_map:
            vacation_map[date_str] = []
        
        vacation_map[date_str].append(staff_name)
    
    return vacation_map


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    print("QGenda API Client")
    print("See docs/qgenda_integration.md for detailed documentation")
    print("\nExample usage:")
    print("  from qgenda_client import QGendaClient")
    print("  client = QGendaClient(api_key='...', company_key='...')")
    print("  schedule = client.get_schedule('2026-01-01', '2026-03-31')")
