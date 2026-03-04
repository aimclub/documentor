# Metrics Calculation Scripts

This folder contains standalone scripts for calculating document parsing quality metrics:

1. **calculate_dedoc_metrics.py** - metrics calculation for Dedoc (PDF, PDF scanned, DOCX)
2. **calculate_marker_metrics.py** - metrics calculation for Marker (PDF)
3. **calculate_documentor_metrics.py** - metrics calculation for DocuMentor (PDF and DOCX; one script, one output)

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

1. **Python 3.10+** installed on your system
2. **Docker** installed (required for Dedoc)
3. **Set up each method according to its requirements** (see detailed sections below)

## Setup and Running Scripts

### 1. Dedoc Metrics Calculation

#### Step 1: Clone Dedoc Repository

```bash
# Navigate to experiments folder
cd experiments

# Clone Dedoc repository (https://github.com/ispras/dedoc)
git clone https://github.com/ispras/dedoc

```

#### Step 2: Create Virtual Environment

```bash
# Create virtual environment for Dedoc
python -m venv venv_dedoc

# Activate virtual environment
# On Windows:
venv_dedoc\Scripts\activate
# On Linux/Mac:
source venv_dedoc/bin/activate
```

#### Step 3: Install Dependencies

```bash
# Upgrade pip
python -m pip install --upgrade pip

# Install required packages
pip install requests
```

#### Step 4: Deploy Dedoc Docker Container

```bash
# From project root
cd dedoc

# Build and run (Dedoc on port 1231; may start Grobid on 8070)
docker compose up --build -d dedoc

# Check
docker ps --filter name=dedoc
```

#### Step 5: Run the Script

```bash
# From experiments folder
# Windows:
venv_dedoc\Scripts\python.exe calculate_dedoc_metrics.py
# Linux/Mac:
venv_dedoc/bin/python calculate_dedoc_metrics.py
```

**Result:** File `dedoc_metrics.json` (in experiments/) with per-document metrics and per-type summaries (`_summary`, `_summary_pdf`, `_summary_pdf_scanned`, `_summary_docx`) for fair comparison with DocuMentor.

**Note:** The script will check if Dedoc API is available at `http://localhost:1231/` before processing documents.

---

### 2. Marker Metrics Calculation

#### Step 1: Clone Marker Repository

```bash
# Navigate to experiments folder
cd experiments

# Clone Marker repository
git clone https://github.com/VikParuchuri/marker.git

```

#### Step 2: Create Virtual Environment

```bash
# Create virtual environment for Marker
python -m venv venv_marker

# Activate virtual environment
# On Windows:
venv_marker\Scripts\activate
# On Linux/Mac:
source venv_marker/bin/activate
```

#### Step 3: Install Marker

```bash
# Upgrade pip
python -m pip install --upgrade pip

# Navigate to Marker directory
cd marker

# Install Marker in editable mode (this will install all dependencies)
pip install -e .

# Return to project root
cd ../
```

#### Step 4: Run the metrics script

```bash
# From experiments folder
# Windows:
venv_marker\Scripts\python.exe calculate_marker_metrics.py
# Linux/Mac:
venv_marker/bin/python calculate_marker_metrics.py
```

**Result:** File `marker_metrics.json` (in experiments/) with per-document metrics (same keys as DocuMentor: `{stem}_pdf`, `{stem}_scanned`), `_summary`, `_summary_pdf`, `_summary_pdf_scanned`.

**Note:**
- Marker processes **all PDFs** in test_files/ (regular and scanned); DOCX is not supported
- If an MD file with the same stem exists next to the PDF, it is used instead of running Marker (faster)
- First run may take longer as Marker downloads required models
- Marker requires significant disk space for models (several GB)

---

### 3. DocuMentor Metrics Calculation

#### Step 1: Install Project Dependencies

DocuMentor is part of this project, so you need to install project dependencies:

```bash
# Navigate to project root
cd /path/to/documentor_langchain

# Create virtual environment (if not already created)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install project dependencies
pip install -e .
```

#### Step 2: Deploy Dots OCR (if required)

If your DocuMentor configuration requires Dots OCR:

```bash
# Follow project documentation for Dots OCR deployment
# Typically involves Docker container or local service
```

#### Step 3: Verify DocuMentor Installation

```bash
# Test import
python -c "from documentor import Pipeline; print('DocuMentor is available')"
```

#### Step 4: Run the Script

```bash
# Make sure virtual environment with project dependencies is activated
python experiments/calculate_documentor_metrics.py
```

**Result:** File `experiments/documentor_metrics.json` with metrics for each document and summary statistics.

**Note:** The script requires DocuMentor to be properly installed and configured. Make sure all project dependencies are installed. The same script processes both PDF and DOCX from `test_files/`; for DOCX it uses many-to-one matching and lenient hierarchy. Each result entry includes `document_type` ("pdf" or "docx"). Use `_summary` and per-document entries to fill `metrics.md`.

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

## Directory Structure

All in `experiments/`:

```
documentor_langchain/
├── experiments/
│   ├── calculate_dedoc_metrics.py
│   ├── calculate_marker_metrics.py
│   ├── calculate_documentor_metrics.py
│   ├── test_marker_output.py   # Optional: see Marker output on one PDF
│   ├── README.md
│   ├── venv_dedoc/             # Virtual environment for Dedoc
│   ├── venv_marker/            # Virtual environment for Marker
│   ├── marker/                  # Marker repository (git clone)
│   ├── dedoc_metrics.json      # Generated after running
│   ├── marker_metrics.json     # Generated after running
│   └── documentor_metrics.json # Generated after running
└── test_files/
```

**Note:** Virtual environment folders (`venv_dedoc/`, `venv_marker/`) and Marker repository (`marker/`) should be added to `.gitignore` if they are not already there.

## Troubleshooting

### Dedoc Issues

- **Container not starting:** Check if port 1231 is already in use: `netstat -an | findstr 1231` (Windows) or `lsof -i :1231` (Linux/Mac)
- **API not responding:** Verify container is running: `docker ps --filter name=dedoc`
- **Connection refused:** Make sure Docker daemon is running

### Marker Issues

- **Import errors:** Make sure you installed Marker in editable mode: `pip install -e .` from `marker/` directory (being in experiments/)
- **Model download failures:** Check internet connection and disk space (models require several GB)
- **CUDA/GPU errors:** Marker will fall back to CPU if GPU is not available, but processing will be slower

### DocuMentor Issues

- **Import errors:** Make sure project dependencies are installed: `pip install -e .` from project root
- **Dots OCR errors:** Verify Dots OCR is deployed and accessible according to project documentation

## Notes

- All scripts are completely standalone and do not depend on other project scripts
- Scripts automatically find documents and corresponding annotations in `test_files/`
- If required files or dependencies are missing, scripts will output clear error messages
- Each script uses its own virtual environment to avoid dependency conflicts
- Virtual environments can be safely deleted and recreated if needed