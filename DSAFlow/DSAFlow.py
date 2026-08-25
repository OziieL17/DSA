"""3D Slicer scripted module entry point for DSAFlow."""

try:
    import os
    import sys
    import qt
    import slicer
    from slicer.ScriptedLoadableModule import ScriptedLoadableModule, ScriptedLoadableModuleWidget, ScriptedLoadableModuleLogic
except ImportError:
    slicer = None
    ScriptedLoadableModule = object
    ScriptedLoadableModuleWidget = object
    ScriptedLoadableModuleLogic = object


class DSAFlow(ScriptedLoadableModule):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.title = "DSA Flow"
        self.parent.categories = ["Vascular Research"]
        self.parent.contributors = ["OziieL17"]
        self.parent.helpText = (
            "Guided research pipeline for cerebral DSA. Step 1 validates the DICOM input "
            "before segmentation or quantitative analysis."
        )
        self.parent.acknowledgementText = "Research software; not for clinical decision-making."


class DSAFlowWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        super().setup()
        self.logic = DSAFlowLogic()

        intro = qt.QLabel(
            "<b>DSA Flow — Input validation</b><br>"
            "1. Import the study with Slicer's DICOM module.<br>"
            "2. Click <i>Scan DICOM database</i>.<br>"
            "3. Review the readiness report before continuing."
        )
        intro.wordWrap = True
        self.layout.addWidget(intro)

        self.scanButton = qt.QPushButton("1. Scan DICOM database")
        self.scanButton.toolTip = "Find 3D subtraction volumes and XA/RF cine series and verify required metadata."
        self.scanButton.connect("clicked()", self.onScan)
        self.layout.addWidget(self.scanButton)

        self.summaryLabel = qt.QLabel("Status: waiting for scan")
        self.summaryLabel.wordWrap = True
        self.layout.addWidget(self.summaryLabel)

        self.results = qt.QTextEdit()
        self.results.readOnly = True
        self.results.minimumHeight = 320
        self.layout.addWidget(self.results)

        self.continueButton = qt.QPushButton("2. Continue to 3D segmentation")
        self.continueButton.enabled = False
        self.continueButton.toolTip = "Enabled only when a valid 3DANGIO SUB volume is detected."
        self.continueButton.connect("clicked()", self.onContinue)
        self.layout.addWidget(self.continueButton)

        note = qt.QLabel(
            "No patient name, ID, birth date, accession number, or other direct identifiers are displayed by this module."
        )
        note.wordWrap = True
        self.layout.addWidget(note)
        self.layout.addStretch(1)

    def onScan(self):
        self.scanButton.enabled = False
        self.summaryLabel.text = "Status: scanning DICOM database…"
        slicer.app.processEvents()
        try:
            reports = self.logic.scanInput()
            self.results.setPlainText(self.logic.formatReports(reports))
            best = self.logic.best3DSub(reports)
            cine = [r for r in reports if r.kind == "XA_CINE" and r.valid]
            if best and best.valid:
                self.summaryLabel.text = (
                    f"READY: valid 3D subtraction volume detected ({best.score}/100); "
                    f"{len(cine)} valid cine series available."
                )
                self.continueButton.enabled = True
            else:
                self.summaryLabel.text = "NOT READY: no valid 3D subtraction volume detected. Review failures below."
                self.continueButton.enabled = False
        except Exception as exc:
            self.summaryLabel.text = "ERROR: input validation could not be completed."
            self.results.setPlainText(str(exc))
            self.continueButton.enabled = False
        finally:
            self.scanButton.enabled = True

    def onContinue(self):
        slicer.util.infoDisplay(
            "Input requirements passed. The next milestone will load the selected 3DANGIO SUB volume and start guided vascular segmentation."
        )


class DSAFlowLogic(ScriptedLoadableModuleLogic):
    def _library(self):
        module_dir = os.path.dirname(os.path.abspath(__file__))
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
        from DSAFlowLib import dicom_io
        return dicom_io

    def scanInput(self):
        return self._library().discover_dsa_series()

    def best3DSub(self, reports):
        candidates = [r for r in reports if r.kind == "3D_SUB"]
        return max(candidates, key=lambda r: (r.valid, r.score, r.file_count), default=None)

    def formatReports(self, reports):
        if not reports:
            return "No supported DSA series were found in the current Slicer DICOM database."
        lines = []
        for r in sorted(reports, key=lambda x: (x.kind, x.description)):
            icon = "PASS" if r.valid else "REVIEW"
            lines.append(f"[{icon}] {r.kind} | {r.description} | score {r.score}/100")
            lines.append(f"  Files: {r.file_count}")
            m = r.metadata
            if r.kind == "3D_SUB":
                lines.append(f"  Matrix: {m.get('rows')} x {m.get('columns')} | spacing: {m.get('pixel_spacing_mm')} mm | slice: {m.get('slice_thickness_mm')} mm")
            elif r.kind == "XA_CINE":
                lines.append(f"  Frames: {m.get('number_of_frames')} | frame time: {m.get('frame_time_ms')} ms | cine rate: {m.get('cine_rate_fps')} fps")
                lines.append(f"  Angles: primary {m.get('primary_angle_deg')}°, secondary {m.get('secondary_angle_deg')}° | SID {m.get('sid_mm')} mm | SOD {m.get('sod_mm')} mm")
            for item in r.warnings:
                lines.append(f"  WARNING: {item}")
            for item in r.failures:
                lines.append(f"  FAIL: {item}")
            lines.append("")
        return "\n".join(lines)
