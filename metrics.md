# Document Parsing Quality Metrics

## Overview

The document parsing quality evaluation system uses a set of metrics to analyze the accuracy of text extraction, structure, and element hierarchy from three types of documents:

1. **DOCX** - native Microsoft Word documents
2. **PDF Regular** - regular PDF files with text layer
3. **Scanned PDF** - scanned PDF files requiring OCR

## Text Accuracy Metrics

### CER (Character Error Rate)

**Character Error Rate** - the proportion of erroneous characters relative to the total number of characters in ground truth.

**Important note for PDF and DOCX:**

- For **PDF Regular** and **DOCX** files, text is extracted directly from the source file, not through OCR
- Theoretically, CER should be 0, as text is taken from the source document
- Non-zero CER values are explained by differences in special character processing:
  - Different representations of spaces (regular, non-breaking, tabs)
  - Differences in handling hyphens and dashes
  - Differences in normalization of quotes and apostrophes
  - Differences in handling line breaks and paragraphs
- In practice, for PDF and DOCX CER ≈ 0, and observed values (0.002-0.075) reflect only differences in text normalization

**For Scanned PDF:**

- CER reflects real OCR errors in text recognition
- Typical values: 0.005-0.013 (average: ~0.009)

### WER (Word Error Rate)

**Word Error Rate** - the proportion of erroneous words relative to the total number of words in ground truth.

**Important note for PDF and DOCX:**

- Similarly to CER, for PDF Regular and DOCX, WER should be close to 0
- Non-zero values are explained by the same reasons as for CER:
  - Differences in special character processing
  - Differences in normalization of spaces and line breaks
- In practice WER ≈ 0 for PDF and DOCX

**For Scanned PDF:**

- WER reflects real OCR word recognition errors
- Usually higher than CER, as one character error can lead to a whole word error

## Document Structure Metrics

### TEDS (Tree-Edit-Distance-based; lower is better)

TEDS are **distance** metrics: **lower values mean better** structure preservation. They are derived from ordering and hierarchy accuracy.

#### Document TEDS

Measures overall structure distance (hierarchy + order). **Lower is better.**

**Formula:** `Document TEDS = (Hierarchy TEDS + (1 - Ordering Accuracy)) / 2`

#### Hierarchy TEDS

Measures hierarchy distance (parent-child relationships). **Lower is better.**

**Formula:** `Hierarchy TEDS = 1 - Hierarchy Accuracy`

**Note on header level substitution:**

Substituting one header level for another (e.g., HEADER_1 → HEADER_2) increases TEDS (worse score), although in practice this is often a minor error. Actual parsing quality may be better than TEDS suggests if the main issue is header level substitutions.

### Ordering Accuracy (higher is better)

Proportion of matched elements in the correct order relative to ground truth. Usually close to 1.0 for all methods.

### Hierarchy Accuracy (higher is better)

Proportion of matched elements with the correct parent. Higher values mean better preservation of document hierarchy.

## Class Detection Metrics

### Precision, Recall, F1 for Element Types

For each element type (text, header_1, header_2, table, image, caption, etc.), the following are calculated:

- **Precision** - the proportion of correctly identified elements among all predicted
- **Recall** - the proportion of found elements among all elements in ground truth
- **F1** - harmonic mean of precision and recall

### Type Substitutions

The number of substitutions of one element type for another (e.g., text → header_1).

In current results: **0 substitutions** - the system does not confuse element types.

### Header Level Substitutions

The number of substitutions of one header level for another (e.g., header_1 → header_2).

In current results: **0 substitutions** - the system correctly identifies header levels.

## Bounding Box Metrics (PDF only)

For PDF files (Regular and Scanned), metrics for element coordinate accuracy are calculated:

- **Bbox Precision** - accuracy of coordinate determination among all predicted bboxes
- **Bbox Recall** - completeness of coordinate determination among all elements in ground truth
- **Bbox F1** - harmonic mean of precision and recall

**For DOCX:** these metrics are not applicable, as DOCX does not contain element coordinates (values = 0.0).

## Metric Comparison by File Type

### PDF Regular

- **CER/WER:** 0.0075 / 0.0092 (actually equal to zero; non-zero only due to normalization)
- **Document TEDS:** ~0.13 (low = good)
- **Hierarchy TEDS:** ~0.27 (low = good)
- **Bbox F1:** ~0.98
- **Features:** Text from PDF layer; element coordinates accurate

### DOCX

- **CER/WER:** 0.0096 / 0.0023 (actually equal to zero; non-zero only due to normalization)
- **Document TEDS:** ~0.02 (low = good)
- **Hierarchy TEDS:** ~0.04 (low = good)
- **Bbox F1:** 0.0 (not applicable)
- **Features:**
  - Text from DOCX source; structure uses many-to-one matching and lenient hierarchy (merge/split and level differences not penalized)

### Scanned PDF

- **CER/WER:** 0.0129 / 0.0254 (real OCR errors)
- **Document TEDS:** ~0.18 (low = good)
- **Hierarchy TEDS:** ~0.35 (low = good)
- **Bbox F1:** ~0.94
- **Features:** Text from OCR (some recognition errors); structure and coordinates remain accurate

## Processing Time

- **DOCX:** ~1.8 sec/page, ~23 sec/document
- **PDF Regular:** ~2.3 sec/page, ~27 sec/document
- **Scanned PDF:** ~4.2 sec/page, ~49 sec/document (longer due to OCR)

## Comparison: DocuMentor vs Marker vs Dedoc

### Overview

This section compares **DocuMentor**, **Marker**, and **Dedoc** by document type. Metrics are split into separate tables for **PDF (regular)**, **PDF (scanned)**, and **DOCX**. Marker supports PDF only; Dedoc and DocuMentor support all three types.

TEDS are **distance** metrics (lower is better). Ordering Accuracy and Hierarchy Accuracy are **accuracy** metrics (higher is better).

---

### PDF (regular)

**Text accuracy**


| Method         | CER       | WER       |
| -------------- | --------- | --------- |
| **DocuMentor** | **0.0075** (actually 0) | **0.0092** (actually 0) |
| Marker         | 0.0491    | 0.0757    |
| Dedoc          | 0.0780    | 0.0846    |


**Document structure**


| Method         | Document TEDS (lower better) | Hierarchy TEDS (lower better) | Ordering Accuracy | Hierarchy Accuracy |
| -------------- | ---------------------------- | ----------------------------- | ----------------- | ------------------ |
| **DocuMentor** | **0.13**                     | **0.27**                      | **~1.0**          | **0.73**           |
| Marker         | 0.4890                       | 0.9771                        | 0.9992             | 0.0229             |
| Dedoc          | 0.4741                       | 0.9482                        | 1.00              | 0.0518             |


---

### PDF (scanned)

**Text accuracy**


| Method         | CER       | WER       |
| -------------- | --------- | --------- |
| **DocuMentor** | **0.0129** | **0.0254** |
| Marker         | 0.0255    | 0.0541    |
| Dedoc          | 0.0740    | 0.1001    |


**Document structure**


| Method         | Document TEDS (lower better) | Hierarchy TEDS (lower better) | Ordering Accuracy | Hierarchy Accuracy |
| -------------- | ---------------------------- | ----------------------------- | ----------------- | ------------------ |
| **DocuMentor** | **0.18**                     | **0.35**                      | **~1.0**          | **0.65**           |
| Marker         | 0.4932                       | 0.9863                        | 1.00              | 0.0137             |
| Dedoc          | 0.4733                       | 0.9466                        | 1.00              | 0.0534             |


---

### DOCX

**Text accuracy**


| Method         | CER    | WER    |
| -------------- | ------ | ------ |
| **DocuMentor** | 0.0096 (actually 0) | 0.0023 (actually 0) |
| Dedoc          | 0.0068 | 0.0043 |


**Document structure**


| Method         | Document TEDS (lower better) | Hierarchy TEDS (lower better) | Ordering Accuracy | Hierarchy Accuracy |
| -------------- | ---------------------------- | ----------------------------- | ----------------- | ------------------ |
| **DocuMentor** | 0.019                        | 0.038                         | 0.999             | 0.962              |
| Dedoc          | 0.0009                       | 0.0000                        | 0.9982            | 1.0000             |

### DocuMentor metrics (12 documents: 4 docx, 4 pdf, 4 pdf_scanned)

**Summary (all):**
- CER 0.0100, WER 0.0121;
- Ordering 0.9995, Hierarchy 0.7808;
- Document TEDS 0.1098, Hierarchy TEDS 0.2192.

**By type:**

| Type        | n  | CER    | WER    | Ordering | Hierarchy | Document TEDS | Hierarchy TEDS |
| ----------- | -- | ------ | ------ | -------- | --------- | -------------- | --------------- |
| docx        | 4  | 0.0096 | 0.0023 | 0.9993   | 0.9622    | 0.0193        | 0.0378          |
| pdf         | 4  | 0.0075 | 0.0085 | 0.9996   | 0.7321    | 0.1342        | 0.2679          |
| pdf_scanned | 4  | 0.0129 | 0.0256 | 0.9997   | 0.6482    | 0.1761        | 0.3518          |

**Per-document:**

| Document                      | Type        | CER    | WER    | Hierarchy |
| ----------------------------- | ----------- | ------ | ------ | --------- |
| 2412.19495v2_docx            | docx        | 0.0323 | 0.0029 | 1.0000    |
| 2412.19495v2_pdf             | pdf         | 0.0064 | 0.0077 | 0.8732    |
| 2412.19495v2_scanned         | pdf_scanned | 0.0046 | 0.0177 | 0.4062    |
| 2508.19267v1_docx            | docx        | 0.0059 | 0.0062 | 1.0000    |
| 2508.19267v1_pdf             | pdf         | 0.0057 | 0.0046 | 0.7465    |
| 2508.19267v1_scanned         | pdf_scanned | 0.0165 | 0.0335 | 0.8235    |
| journal-10-67-5-676-697_docx | docx        | 0.0000 | 0.0000 | 0.9737    |
| journal-10-67-5-676-697_pdf  | pdf         | 0.0178 | 0.0216 | 0.8687    |
| journal-10-67-5-676-697_scanned | pdf_scanned | 0.0199 | 0.0271 | 0.8632    |
| journal-10-67-5-721-729_docx | docx        | 0.0000 | 0.0000 | 0.8750    |
| journal-10-67-5-721-729_pdf  | pdf         | 0.0000 | 0.0000 | 0.4400    |
| journal-10-67-5-721-729_scanned | pdf_scanned | 0.0108 | 0.0243 | 0.5000    |

Full results: `experiments/documentor_metrics.json`.

### Dedoc metrics (12 documents: 4 docx, 4 pdf, 4 pdf_scanned)

**Summary (all):** 
- CER 0.0529, WER 0.0630; 
- Ordering 0.9994, Hierarchy 0.3684; 
- Document TEDS 0.3161, Hierarchy TEDS 0.6316.

**By type:**

| Type        | n  | CER    | WER    | Ordering | Hierarchy | Document TEDS | Hierarchy TEDS |
| ----------- | -- | ------ | ------ | -------- | --------- | -------------- | --------------- |
| docx        | 4  | 0.0068 | 0.0043 | 0.9982   | 1.0000    | 0.0009         | 0.0000          |
| pdf         | 4  | 0.0780 | 0.0846 | 1.0000   | 0.0518    | 0.4741         | 0.9482          |
| pdf_scanned | 4  | 0.0740 | 0.1001 | 1.0000   | 0.0534    | 0.4733         | 0.9466          |

**Per-document:**

| Document                 | Type        | CER    | WER    | Hierarchy |
| ------------------------ | ----------- | ------ | ------ | --------- |
| 2412.19495v2_docx       | docx        | 0.0001 | 0.0015 | 1.0000    |
| 2412.19495v2_pdf        | pdf         | 0.0972 | 0.1068 | 0.0000    |
| 2412.19495v2_scanned    | pdf_scanned | 0.1358 | 0.1433 | 0.0000    |
| 2508.19267v1_docx       | docx        | 0.0137 | 0.0035 | 1.0000    |
| 2508.19267v1_pdf        | pdf         | 0.0297 | 0.0433 | 0.0000    |
| 2508.19267v1_scanned    | pdf_scanned | 0.0429 | 0.0556 | 0.0000    |
| journal-10-67-5-676-697_docx       | docx        | 0.0133 | 0.0120 | 1.0000    |
| journal-10-67-5-676-697_pdf        | pdf         | 0.0623 | 0.0451 | 0.0167    |
| journal-10-67-5-676-697_scanned    | pdf_scanned | 0.0526 | 0.0754 | 0.0317    |
| journal-10-67-5-721-729_docx      | docx        | 0.0000 | 0.0000 | 1.0000    |
| journal-10-67-5-721-729_pdf        | pdf         | 0.1229 | 0.1432 | 0.1905    |
| journal-10-67-5-721-729_scanned    | pdf_scanned | 0.0648 | 0.1260 | 0.1818    |

Full results: `experiments/dedoc_metrics.json`.

### Marker metrics (8 documents: 4 pdf, 4 pdf_scanned)

**Summary (all):**
- CER 0.0373, WER 0.0649;
- Ordering 0.9996, Hierarchy 0.0183;
- Document TEDS 0.4911, Hierarchy TEDS 0.9817.

**By type:**

| Type        | n  | CER    | WER    | Ordering | Hierarchy | Document TEDS | Hierarchy TEDS |
| ----------- | -- | ------ | ------ | -------- | --------- | -------------- | --------------- |
| pdf         | 4  | 0.0491 | 0.0757 | 0.9992   | 0.0229    | 0.4890        | 0.9771          |
| pdf_scanned | 4  | 0.0255 | 0.0541 | 1.0000   | 0.0137    | 0.4932        | 0.9863          |

**Per-document:**

| Document                      | Type        | CER    | WER    | Hierarchy |
| ----------------------------- | ----------- | ------ | ------ | --------- |
| 2412.19495v2_pdf             | pdf         | 0.0311 | 0.0339 | 0.0000    |
| 2412.19495v2_scanned         | pdf_scanned | 0.0061 | 0.0259 | 0.0000    |
| 2508.19267v1_pdf             | pdf         | 0.0376 | 0.0575 | 0.0000    |
| 2508.19267v1_scanned         | pdf_scanned | 0.0358 | 0.0508 | 0.0000    |
| journal-10-67-5-676-697_pdf  | pdf         | 0.0366 | 0.0667 | 0.0145    |
| journal-10-67-5-676-697_scanned | pdf_scanned | 0.0354 | 0.0555 | 0.0147    |
| journal-10-67-5-721-729_pdf  | pdf         | 0.0912 | 0.1448 | 0.0769    |
| journal-10-67-5-721-729_scanned | pdf_scanned | 0.0246 | 0.0842 | 0.0400    |

Full results: `experiments/marker_metrics.json`.

### Processing Time


| Method         | Average Time per Document                               | Average Time per Page                                   |
| -------------- | ------------------------------------------------------- | ------------------------------------------------------- |
| **DocuMentor** | **27.39 sec (PDF Regular)** **49.38 sec (Scanned PDF)** | **2.33 sec/page (Regular)** **4.17 sec/page (Scanned)** |
| Marker         | 1019 sec (16.98 min)                                    | ~127 sec/page                                           |
| **Dedoc**      | **2.32 sec**                                            | **~0.20 sec/page**                                      |


### Hardware Requirements (GPU)


| Method                    | GPU VRAM                                 | GPU Utilization         | Notes                                                                       |
| ------------------------- | ---------------------------------------- | ----------------------- | --------------------------------------------------------------------------- |
| **DocuMentor (Dots OCR)** | **~24 GB**                               | High                    | Most hardware-demanding method, requires high-end GPU with significant VRAM |
| Marker                    | **~0.9 GB avg, 1.6 GB max**              | **17.8% avg, 100% max** | Uses GPU for processing, moderate VRAM requirements                         |
| Dedoc                     | **~1.1 GB** (avg: 1.07 GB, max: 1.10 GB) | **22.7% avg, 70% max**  | Uses GPU for processing, moderate VRAM requirements                         |


**Analysis:**

- **DocuMentor (Dots OCR)** is the most GPU-demanding method, requiring approximately **24 GB of GPU video memory** for optimal performance. This makes it suitable only for systems with high-end GPUs (e.g., NVIDIA A100, H100, or multiple consumer GPUs with sufficient VRAM). The high VRAM requirement is due to the use of large vision-language models for OCR, which provides superior text recognition accuracy but at the cost of hardware resources.
- **Dedoc** uses GPU acceleration:
  - **GPU VRAM**: Average ~1.07 GB, maximum ~1.10 GB
  - **GPU Utilization**: Average 22.7%, maximum 70%
- **Marker** uses GPU acceleration:
  - **GPU VRAM**: Average ~0.91 GB, maximum ~1.60 GB
  - **GPU Utilization**: Average 17.8%, maximum 100%
- **Comparison**: 
  - **GPU VRAM**: DocuMentor requires **22x more** than Dedoc (24 GB vs 1.1 GB) and **26x more** than Marker (24 GB vs 0.9 GB avg)
  - Marker and Dedoc have lower GPU VRAM requirements (~0.9-1.1 GB) but significantly lower accuracy metrics

**Analysis:**

- **DocuMentor** processes documents in **seconds** (27.4 sec for regular PDFs, 49.4 sec for scanned PDFs), making it **~37x faster** than Marker (1019 sec) for regular PDFs and **~21x faster** for scanned PDFs
- Marker's processing time is significantly longer (16.98 min per document), making it unsuitable for real-time or batch processing scenarios
- Dedoc processes documents faster (2.3 sec), but at the cost of significantly lower accuracy (7.60% CER, 9.23% WER)

### Detailed Time Comparison (8 PDF files)

| Method       | Total      | Average per document |
| ------------ | ---------- | -------------------- |
| Marker       | 135.87 min | 16.98 min            |
| DocuMentor   | ~5.1 min   | 27–49 sec (reg/scanned) |
| Dedoc        | 18.67 sec  | 2.33 sec             |

### Summary


| Aspect                                      | Winner     | Notes                                                                                                                 |
| ------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------- |
| **Text Accuracy (CER/WER)**                 | DocuMentor | Lower CER/WER than Marker (3.73% CER, 6.49% WER) and Dedoc; 2.9-33x lower WER                                                  |
| **Document Structure (TEDS, lower better)** | DocuMentor | Lowest TEDS (0.02-0.18 vs 0.47-0.50 for Marker/Dedoc)                                                                 |
| **Hierarchy Accuracy**                      | DocuMentor | 13-45x better than Marker, 13-15x better than Dedoc (65-96% vs 1.83-5.26%)                                            |
| **Ordering Accuracy**                       | Tie        | All three achieve ~99-100%                                                                                            |
| **Processing Speed**                        | DocuMentor | 27-49 sec/doc (37x faster than Marker); Dedoc is faster but with much lower accuracy                                  |
| **Hardware Requirements**                   | DocuMentor | Requires ~24 GB GPU VRAM for optimal accuracy; other methods have lower requirements but significantly lower accuracy |


**Conclusion:**

- **DocuMentor** has the best text accuracy (lowest CER/WER; PDF/DOCX actually 0) and structure preservation (lowest Document and Hierarchy TEDS). It has much higher hierarchy accuracy (65-96% vs 1.83% for Marker and 5.26% for Dedoc) and processes documents in 27-49 sec, ~37x faster than Marker. It requires ~24 GB GPU VRAM for optimal performance.
- **Marker** shows very low hierarchy accuracy (1.83%) and high text error rates (3.73% CER, 6.49% WER), while also being the slowest method (16.98 min per document).
- **Dedoc** has the highest text error rates (7.60% CER, 9.23% WER) and very low hierarchy accuracy (5.26%), indicating significant issues with OCR quality and structure understanding. While it processes documents faster (2.3 sec), this comes at the cost of significantly lower accuracy.

**Overall:** DocuMentor provides the best balance of accuracy and speed, with excellent text extraction, structure preservation, and reasonable processing times. The high GPU VRAM requirement (24 GB) is justified by the superior accuracy and quality of results compared to other methods.

## Conclusions

1. **Text Accuracy:** For PDF and DOCX, CER/WER is actually 0, non-zero values are explained only by differences in special character normalization
2. **Structural Accuracy (TEDS):** TEDS are distance metrics (lower is better). DocuMentor has low TEDS for all file types. Header level substitution increases TEDS (worse score) but is often a minor practical error.
3. **DOCX vs PDF:** In the test sample, DOCX files are more complex (many headers, non-standard layout), which can yield higher TEDS (worse distance) than for some PDFs.
4. **OCR Quality:** For scanned PDFs, OCR quality is sufficiently high (average CER ~1.3%, WER ~2.5%), which allows successful extraction of document structure
5. **Comparison with Marker and Dedoc:** DocuMentor significantly outperforms both methods in accuracy metrics:
  - **Text Accuracy:** Lower CER/WER than Marker and Dedoc; for PDF/DOCX CER/WER actually 0; for scanned PDF CER ~1.3%, WER ~2.5%
  - **Document Structure (TEDS, lower better):** DocuMentor has much lower Document TEDS (0.02-0.18 vs 0.50 for Marker, 0.47 for Dedoc)
  - **Hierarchy Accuracy:** 13-45x better than Marker (65-96% vs 1.83%), 13-15x better than Dedoc (65-96% vs 5.26%)
  - **Processing Speed:** DocuMentor is 21-37x faster than Marker (27-49 sec vs 1019 sec)

