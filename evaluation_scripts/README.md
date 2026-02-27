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

1. **Python 3.10+** installed on your system
2. **Docker** installed (required for Dedoc)
3. **Set up each method according to its requirements** (see detailed sections below)

## Setup and Running Scripts

### 1. Dedoc Metrics Calculation

#### Step 1: Create Virtual Environment

```bash
# Navigate to project root
cd /path/to/documentor_langchain

# Create virtual environment for Dedoc
python -m venv evaluation_scripts/venv_dedoc

# Activate virtual environment
# On Windows:
evaluation_scripts\venv_dedoc\Scripts\activate
# On Linux/Mac:
source evaluation_scripts/venv_dedoc/bin/activate
```

#### Step 2: Install Dependencies

```bash
# Upgrade pip
python -m pip install --upgrade pip

# Install required packages
pip install requests
```

#### Step 3: Deploy Dedoc Docker Container

```bash
# Pull and run Dedoc Docker container
docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc

# Verify container is running
docker ps --filter name=dedoc

# If container already exists but is stopped, start it:
docker start dedoc
```

#### Step 4: Run the Script

```bash
# Make sure virtual environment is activated
# On Windows:
evaluation_scripts\venv_dedoc\Scripts\python.exe evaluation_scripts\calculate_dedoc_metrics.py
# On Linux/Mac:
evaluation_scripts/venv_dedoc/bin/python evaluation_scripts/calculate_dedoc_metrics.py
```

**Result:** File `evaluation_scripts/dedoc_metrics.json` with metrics for each document and summary statistics.

**Note:** The script will check if Dedoc API is available at `http://localhost:1231/` before processing documents.

---

### 2. Marker Metrics Calculation

#### Step 1: Clone Marker Repository

```bash
# Navigate to evaluation_scripts folder
cd evaluation_scripts

# Clone Marker repository
git clone https://github.com/VikParuchuri/marker.git

# Verify Marker repository is cloned
ls marker/
```

#### Step 2: Create Virtual Environment

```bash
# Navigate to project root
cd /path/to/documentor_langchain

# Create virtual environment for Marker
python -m venv evaluation_scripts/venv_marker

# Activate virtual environment
# On Windows:
evaluation_scripts\venv_marker\Scripts\activate
# On Linux/Mac:
source evaluation_scripts/venv_marker/bin/activate
```

#### Step 3: Install Marker

```bash
# Upgrade pip
python -m pip install --upgrade pip

# Navigate to Marker directory
cd evaluation_scripts/marker

# Install Marker in editable mode (this will install all dependencies)
pip install -e .

# Return to project root
cd ../..
```

**Note:** Marker installation will automatically download required models on first use. The installation may take some time as it includes PyTorch and other ML dependencies.

#### Step 4: Run the Script

```bash
# Make sure virtual environment is activated
# On Windows:
evaluation_scripts\venv_marker\Scripts\python.exe evaluation_scripts\calculate_marker_metrics.py
# On Linux/Mac:
evaluation_scripts/venv_marker/bin/python evaluation_scripts/calculate_marker_metrics.py
```

**Result:** File `evaluation_scripts/marker_metrics.json` with metrics for each document and summary statistics.

**Note:** 
- The script will automatically find MD files in document folders (if they exist) or process PDF through Marker if MD files are missing
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
python evaluation_scripts/calculate_documentor_metrics.py
```

**Result:** File `evaluation_scripts/documentor_metrics.json` with metrics for each document and summary statistics.

**Note:** The script requires DocuMentor to be properly installed and configured. Make sure all project dependencies are installed.

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

After setup, your `evaluation_scripts/` folder should look like this:

```
evaluation_scripts/
├── calculate_dedoc_metrics.py
├── calculate_marker_metrics.py
├── calculate_documentor_metrics.py
├── README.md
├── venv_dedoc/              # Virtual environment for Dedoc (created during setup)
│   ├── Scripts/             # Windows
│   └── bin/                  # Linux/Mac
├── venv_marker/             # Virtual environment for Marker (created during setup)
│   ├── Scripts/             # Windows
│   └── bin/                  # Linux/Mac
├── marker/                   # Marker repository (cloned during setup)
│   ├── marker/
│   ├── pyproject.toml
│   └── ...
├── dedoc_metrics.json        # Results file (generated after running)
├── marker_metrics.json        # Results file (generated after running)
└── documentor_metrics.json   # Results file (generated after running)
```

**Note:** Virtual environment folders (`venv_dedoc/`, `venv_marker/`) and Marker repository (`marker/`) should be added to `.gitignore` if they are not already there.

## Troubleshooting

### Dedoc Issues

- **Container not starting:** Check if port 1231 is already in use: `netstat -an | findstr 1231` (Windows) or `lsof -i :1231` (Linux/Mac)
- **API not responding:** Verify container is running: `docker ps --filter name=dedoc`
- **Connection refused:** Make sure Docker daemon is running

### Marker Issues

- **Import errors:** Make sure you installed Marker in editable mode: `pip install -e .` from `evaluation_scripts/marker/` directory
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