"""
Data Processing Module

This module provides data transformation, validation, and pipeline utilities
for processing various data formats including CSV, JSON, and streaming data.

Author: TechCorp Data Engineering Team
Version: 1.5.0
"""

import csv
import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Generic,
    Iterator,
    List,
    Optional,
    TypeVar,
    Union,
)
import re

logger = logging.getLogger(__name__)

T = TypeVar('T')
InputT = TypeVar('InputT')
OutputT = TypeVar('OutputT')


class DataValidationError(Exception):
    """Raised when data validation fails."""
    def __init__(self, message: str, errors: list = None):
        super().__init__(message)
        self.errors = errors or []


class ProcessingError(Exception):
    """Raised when data processing fails."""
    pass


class DataFormat(Enum):
    """Supported data formats."""
    JSON = "json"
    CSV = "csv"
    JSONL = "jsonl"
    PARQUET = "parquet"


@dataclass
class ValidationRule:
    """Defines a validation rule for data fields."""
    field_name: str
    validator: Callable[[Any], bool]
    error_message: str
    required: bool = True


@dataclass
class ProcessingStats:
    """Statistics from data processing operations."""
    total_records: int = 0
    processed_records: int = 0
    failed_records: int = 0
    skipped_records: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate processing duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_records == 0:
            return 0.0
        return (self.processed_records / self.total_records) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "failed_records": self.failed_records,
            "skipped_records": self.skipped_records,
            "success_rate": f"{self.success_rate:.2f}%",
            "duration_seconds": self.duration_seconds,
            "error_count": len(self.errors)
        }


class DataValidator:
    """Validates data against defined rules."""
    
    def __init__(self):
        self.rules: List[ValidationRule] = []
        self._builtin_validators = {
            'email': self._validate_email,
            'phone': self._validate_phone,
            'url': self._validate_url,
            'date': self._validate_date,
            'positive_number': lambda x: isinstance(x, (int, float)) and x > 0,
            'non_empty_string': lambda x: isinstance(x, str) and len(x.strip()) > 0,
        }

    def add_rule(self, rule: ValidationRule) -> 'DataValidator':
        """Add a validation rule."""
        self.rules.append(rule)
        return self

    def add_builtin_rule(
        self,
        field_name: str,
        validator_name: str,
        required: bool = True
    ) -> 'DataValidator':
        """Add a built-in validation rule."""
        if validator_name not in self._builtin_validators:
            raise ValueError(f"Unknown validator: {validator_name}")
        
        rule = ValidationRule(
            field_name=field_name,
            validator=self._builtin_validators[validator_name],
            error_message=f"Invalid {validator_name} format for {field_name}",
            required=required
        )
        return self.add_rule(rule)

    def validate(self, data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate data against all rules.
        
        Args:
            data: Dictionary of field names to values
            
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        
        for rule in self.rules:
            value = data.get(rule.field_name)
            
            # Check required fields
            if value is None:
                if rule.required:
                    errors.append(f"Missing required field: {rule.field_name}")
                continue
            
            # Run validator
            try:
                if not rule.validator(value):
                    errors.append(rule.error_message)
            except Exception as e:
                errors.append(f"Validation error for {rule.field_name}: {str(e)}")
        
        return len(errors) == 0, errors

    @staticmethod
    def _validate_email(value: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, str(value)))

    @staticmethod
    def _validate_phone(value: str) -> bool:
        """Validate phone number format."""
        # Remove common separators
        cleaned = re.sub(r'[\s\-\.\(\)]', '', str(value))
        # Check if it's a valid phone number (10-15 digits, optional + prefix)
        return bool(re.match(r'^\+?\d{10,15}$', cleaned))

    @staticmethod
    def _validate_url(value: str) -> bool:
        """Validate URL format."""
        pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return bool(re.match(pattern, str(value), re.IGNORECASE))

    @staticmethod
    def _validate_date(value: str) -> bool:
        """Validate ISO date format."""
        try:
            datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return True
        except ValueError:
            return False


class Transformer(ABC, Generic[InputT, OutputT]):
    """Abstract base class for data transformers."""
    
    @abstractmethod
    def transform(self, data: InputT) -> OutputT:
        """Transform input data to output format."""
        pass

    def __call__(self, data: InputT) -> OutputT:
        """Allow transformer to be called as function."""
        return self.transform(data)


class FieldMapper(Transformer[Dict, Dict]):
    """Maps fields from source to target schema."""
    
    def __init__(self, mapping: Dict[str, str]):
        """
        Initialize with field mapping.
        
        Args:
            mapping: Dict of source_field -> target_field
        """
        self.mapping = mapping

    def transform(self, data: Dict) -> Dict:
        """Apply field mapping to data."""
        result = {}
        for source, target in self.mapping.items():
            if source in data:
                result[target] = data[source]
        return result


class FieldTransformer(Transformer[Dict, Dict]):
    """Applies transformations to specific fields."""
    
    def __init__(self):
        self.transformations: Dict[str, Callable] = {}

    def add_transformation(
        self,
        field: str,
        func: Callable[[Any], Any]
    ) -> 'FieldTransformer':
        """Add a transformation for a field."""
        self.transformations[field] = func
        return self

    def transform(self, data: Dict) -> Dict:
        """Apply all transformations."""
        result = data.copy()
        for field, func in self.transformations.items():
            if field in result:
                result[field] = func(result[field])
        return result


class DataPipeline(Generic[T]):
    """
    Chainable data processing pipeline.
    
    Allows composing multiple transformations and processors
    into a single pipeline that can be applied to data streams.
    """
    
    def __init__(self):
        self.steps: List[Callable[[T], T]] = []
        self.validators: List[DataValidator] = []
        self.on_error: Callable[[Exception, T], T] = None
        self.stats = ProcessingStats()

    def add_step(self, step: Callable[[T], T]) -> 'DataPipeline[T]':
        """Add a processing step to the pipeline."""
        self.steps.append(step)
        return self

    def add_transformer(self, transformer: Transformer) -> 'DataPipeline[T]':
        """Add a transformer to the pipeline."""
        return self.add_step(transformer)

    def add_validator(self, validator: DataValidator) -> 'DataPipeline[T]':
        """Add a validator to run before processing."""
        self.validators.append(validator)
        return self

    def set_error_handler(
        self,
        handler: Callable[[Exception, T], T]
    ) -> 'DataPipeline[T]':
        """Set custom error handler."""
        self.on_error = handler
        return self

    def process_one(self, item: T) -> Optional[T]:
        """
        Process a single item through the pipeline.
        
        Args:
            item: Item to process
            
        Returns:
            Processed item or None if validation/processing failed
        """
        # Run validators
        for validator in self.validators:
            is_valid, errors = validator.validate(item)
            if not is_valid:
                self.stats.failed_records += 1
                self.stats.errors.extend(errors)
                return None
        
        # Run pipeline steps
        result = item
        for step in self.steps:
            try:
                result = step(result)
            except Exception as e:
                if self.on_error:
                    result = self.on_error(e, item)
                else:
                    self.stats.failed_records += 1
                    self.stats.errors.append(str(e))
                    return None
        
        self.stats.processed_records += 1
        return result

    def process_batch(self, items: List[T]) -> List[T]:
        """
        Process a batch of items.
        
        Args:
            items: List of items to process
            
        Returns:
            List of successfully processed items
        """
        self.stats = ProcessingStats()
        self.stats.start_time = datetime.utcnow()
        self.stats.total_records = len(items)
        
        results = []
        for item in items:
            result = self.process_one(item)
            if result is not None:
                results.append(result)
        
        self.stats.end_time = datetime.utcnow()
        return results

    def process_stream(
        self,
        items: Iterator[T]
    ) -> Generator[T, None, ProcessingStats]:
        """
        Process items from an iterator as a stream.
        
        Args:
            items: Iterator of items
            
        Yields:
            Successfully processed items
            
        Returns:
            Processing statistics
        """
        self.stats = ProcessingStats()
        self.stats.start_time = datetime.utcnow()
        
        for item in items:
            self.stats.total_records += 1
            result = self.process_one(item)
            if result is not None:
                yield result
        
        self.stats.end_time = datetime.utcnow()
        return self.stats


class CSVProcessor:
    """Process CSV files with streaming support."""
    
    def __init__(
        self,
        delimiter: str = ',',
        encoding: str = 'utf-8',
        skip_header: bool = False
    ):
        self.delimiter = delimiter
        self.encoding = encoding
        self.skip_header = skip_header

    def read_file(self, filepath: Union[str, Path]) -> Generator[Dict, None, None]:
        """
        Read CSV file and yield rows as dictionaries.
        
        Args:
            filepath: Path to CSV file
            
        Yields:
            Dictionary for each row with column headers as keys
        """
        filepath = Path(filepath)
        
        with open(filepath, 'r', encoding=self.encoding) as f:
            reader = csv.DictReader(f, delimiter=self.delimiter)
            for row in reader:
                yield dict(row)

    def write_file(
        self,
        filepath: Union[str, Path],
        data: List[Dict],
        fieldnames: List[str] = None
    ) -> int:
        """
        Write data to CSV file.
        
        Args:
            filepath: Output file path
            data: List of dictionaries to write
            fieldnames: Column names (auto-detected if not provided)
            
        Returns:
            Number of rows written
        """
        if not data:
            return 0
        
        filepath = Path(filepath)
        fieldnames = fieldnames or list(data[0].keys())
        
        with open(filepath, 'w', encoding=self.encoding, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=self.delimiter)
            writer.writeheader()
            writer.writerows(data)
        
        return len(data)


class JSONProcessor:
    """Process JSON and JSONL files."""
    
    def __init__(self, encoding: str = 'utf-8', indent: int = 2):
        self.encoding = encoding
        self.indent = indent

    def read_json(self, filepath: Union[str, Path]) -> Any:
        """Read entire JSON file."""
        with open(filepath, 'r', encoding=self.encoding) as f:
            return json.load(f)

    def write_json(self, filepath: Union[str, Path], data: Any) -> None:
        """Write data to JSON file."""
        with open(filepath, 'w', encoding=self.encoding) as f:
            json.dump(data, f, indent=self.indent, ensure_ascii=False)

    def read_jsonl(
        self,
        filepath: Union[str, Path]
    ) -> Generator[Dict, None, None]:
        """Read JSONL file line by line."""
        with open(filepath, 'r', encoding=self.encoding) as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def write_jsonl(
        self,
        filepath: Union[str, Path],
        data: Iterator[Dict]
    ) -> int:
        """Write data to JSONL file."""
        count = 0
        with open(filepath, 'w', encoding=self.encoding) as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
                count += 1
        return count


class DataAggregator:
    """Aggregate data with various operations."""
    
    def __init__(self):
        self._data: List[Dict] = []

    def add(self, item: Dict) -> 'DataAggregator':
        """Add item to aggregator."""
        self._data.append(item)
        return self

    def add_batch(self, items: List[Dict]) -> 'DataAggregator':
        """Add multiple items."""
        self._data.extend(items)
        return self

    def count(self) -> int:
        """Count total items."""
        return len(self._data)

    def sum(self, field: str) -> float:
        """Sum values of a numeric field."""
        return sum(
            item.get(field, 0) for item in self._data
            if isinstance(item.get(field), (int, float))
        )

    def average(self, field: str) -> Optional[float]:
        """Calculate average of a numeric field."""
        values = [
            item[field] for item in self._data
            if field in item and isinstance(item[field], (int, float))
        ]
        return sum(values) / len(values) if values else None

    def group_by(self, field: str) -> Dict[Any, List[Dict]]:
        """Group items by field value."""
        groups = defaultdict(list)
        for item in self._data:
            key = item.get(field)
            groups[key].append(item)
        return dict(groups)

    def filter(self, predicate: Callable[[Dict], bool]) -> 'DataAggregator':
        """Filter items matching predicate."""
        result = DataAggregator()
        result._data = [item for item in self._data if predicate(item)]
        return result

    def sort(self, field: str, reverse: bool = False) -> 'DataAggregator':
        """Sort items by field."""
        result = DataAggregator()
        result._data = sorted(
            self._data,
            key=lambda x: x.get(field, ''),
            reverse=reverse
        )
        return result

    def to_list(self) -> List[Dict]:
        """Get all items as list."""
        return self._data.copy()


# Example usage and factory functions
def create_user_pipeline() -> DataPipeline:
    """Create a pipeline for processing user data."""
    validator = DataValidator()
    validator.add_builtin_rule('email', 'email')
    validator.add_builtin_rule('name', 'non_empty_string')
    validator.add_rule(ValidationRule(
        field_name='age',
        validator=lambda x: isinstance(x, int) and 0 < x < 150,
        error_message="Age must be between 0 and 150"
    ))
    
    transformer = FieldTransformer()
    transformer.add_transformation('email', lambda x: x.lower().strip())
    transformer.add_transformation('name', lambda x: x.strip().title())
    
    pipeline = DataPipeline()
    pipeline.add_validator(validator)
    pipeline.add_transformer(transformer)
    
    return pipeline


if __name__ == "__main__":
    # Example: Process user data
    pipeline = create_user_pipeline()
    
    users = [
        {"name": "  john doe  ", "email": "JOHN@EXAMPLE.COM", "age": 30},
        {"name": "jane smith", "email": "jane@example.com", "age": 25},
        {"name": "", "email": "invalid", "age": -5},  # Will fail validation
    ]
    
    results = pipeline.process_batch(users)
    
    print(f"Processed {len(results)} of {len(users)} users")
    print(f"Stats: {pipeline.stats.to_dict()}")
    
    for user in results:
        print(f"  - {user['name']} ({user['email']})")
