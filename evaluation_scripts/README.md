# Metrics Calculation Scripts

This folder contains three standalone scripts for calculating document parsing quality metrics:

1. **calculate_dedoc_metrics.py** - metrics calculation for Dedoc
2. **calculate_marker_metrics.py** - metrics calculation for Marker
3. **calculate_documentor_metrics.py** - metrics calculation for DocuMentor

All scripts work with documents from the `test_files/` folder in the project root.

## test_files/ Structure

```
test_files/
  ├── {document_name}/
  │   ├── {document_name}.pdf
  │   ├── {document_name}.docx
  │   └── annotations/
  │       ├── {document_name}.pdf_annotation.json
  │       ├── {document_name}.docx_annotation.json
  │       └── {document_name}_scanned_annotation.json
  └── ...
```

## Prerequisites

Before running any script, you need to:

1. **Download repositories:**
   - Clone or download the required repositories for each method
   - Ensure all dependencies are properly installed

2. **Set up each method according to its requirements** (see sections below)

## Running Scripts

### 1. Dedoc Metrics Calculation

**Requirements:**
- **Download Dedoc repository** and install dependencies
- **Deploy Docker container** with Dedoc:
  ```bash
  docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc
  ```
- `requests` package must be installed

**Run:**
```bash
# Make sure Docker container is running
docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc

# Run the script
python evaluation_scripts/calculate_dedoc_metrics.py
```

**Result:** File `evaluation_scripts/dedoc_metrics.json` with metrics for each document and summary statistics.

### 2. Marker Metrics Calculation

**Requirements:**
- **Download Marker repository** and install dependencies
- **Find/download Marker models** - models must be available in the Marker installation directory
- Marker installed in `experiments/pdf_text_extraction/marker_local` or `venv_marker`
- Or MD files already processed and located in document folders in `test_files/`

**Run:**
```bash
python evaluation_scripts/calculate_marker_metrics.py
```

**Note:** The script will automatically find MD files in document folders or process PDF through Marker if MD files are missing.

**Result:** File `evaluation_scripts/marker_metrics.json` with metrics for each document and summary statistics.

### 3. DocuMentor Metrics Calculation

**Requirements:**
- **Download DocuMentor repository** and install dependencies
- **Deploy Dots OCR** - Dots OCR must be deployed and accessible (see project documentation for deployment instructions)
- DocuMentor installed and available for import
- All project dependencies installed

**Run:**
```bash
python evaluation_scripts/calculate_documentor_metrics.py
```

**Result:** File `evaluation_scripts/documentor_metrics.json` with metrics for each document and summary statistics.

## Calculated Metrics

All scripts calculate the following metrics:

- **CER (Character Error Rate)** - percentage of errors at character level
- **WER (Word Error Rate)** - percentage of errors at word level
- **Ordering Accuracy** - accuracy of element ordering
- **Hierarchy Accuracy** - accuracy of element hierarchy
- **Document TEDS** - Tree-Edit-Distance-based Similarity for document
- **Hierarchy TEDS** - Tree-Edit-Distance-based Similarity for hierarchy
- **Processing Time** - document processing time

## Results Format

Results are saved to JSON files with the following structure:

```json
{
  "document_name": {
    "document_id": "...",
    "cer": 0.0123,
    "wer": 0.0234,
    "ordering_accuracy": 0.9876,
    "hierarchy_accuracy": 0.9543,
    "document_teds": 0.0234,
    "hierarchy_teds": 0.0457,
    "total_elements_gt": 150,
    "total_elements_pred": 148,
    "matched_elements": 145,
    "processing_time": 2.34
  },
  "_summary": {
    "total_files": 4,
    "avg_cer": 0.0123,
    "avg_wer": 0.0234,
    ...
  }
}
```

## Notes

- All scripts are completely standalone and do not depend on other project scripts
- Scripts automatically find documents and corresponding annotations in `test_files/`
- If required files or dependencies are missing, scripts will output clear error messages
