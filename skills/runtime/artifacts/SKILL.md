---
name: artifacts
description: Generate supported text, Word and spreadsheet outputs.
---

Resources: typed document_create, document_update, project file_edit, deterministic DOCX/XLSX generators and readback validation. Select the requested destination: project files and Knowledge documents are different. Supply the generator contract rather than escaped source or a fake download path. Preserve requested content, structure and numbers. Return the actual artifact identity/path from the tool and its validation result. Only advertise formats and transformations exposed by the current tool catalog; Python libraries installed internally are not arbitrary model tools.
