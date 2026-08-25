"""3D Slicer scripted module entry point for DSAFlow."""

try:
    import os, sys
    import qt, slicer
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
        self.parent.helpText = "Guided research pipeline for cerebral DSA segmentation and flow analysis."
        self.parent.acknowledgementText = "Research software; not for clinical decision-making."


class DSAFlowWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        super().setup()
        self.logic = DSAFlowLogic()
        self.reports = []
        self.volumeNode = None
        self.segmentationNode = None

        intro = qt.QLabel("<b>DSA Flow</b><br>Guided workflow: validate → load 3D SUB → preview → adjust → accept.")
        intro.wordWrap = True
        self.layout.addWidget(intro)

        self.scanButton = qt.QPushButton("1. Scan DICOM database")
        self.scanButton.connect("clicked()", self.onScan)
        self.layout.addWidget(self.scanButton)

        self.summaryLabel = qt.QLabel("Status: waiting for scan")
        self.summaryLabel.wordWrap = True
        self.layout.addWidget(self.summaryLabel)

        self.results = qt.QTextEdit()
        self.results.readOnly = True
        self.results.minimumHeight = 220
        self.layout.addWidget(self.results)

        self.loadButton = qt.QPushButton("2. Load best 3D subtraction volume")
        self.loadButton.enabled = False
        self.loadButton.connect("clicked()", self.onLoadVolume)
        self.layout.addWidget(self.loadButton)

        self.volumeStatus = qt.QLabel("3D volume: not loaded")
        self.volumeStatus.wordWrap = True
        self.layout.addWidget(self.volumeStatus)

        thresholdRow = qt.QHBoxLayout()
        thresholdRow.addWidget(qt.QLabel("Lower threshold:"))
        self.thresholdSpin = qt.QDoubleSpinBox()
        self.thresholdSpin.decimals = 1
        self.thresholdSpin.minimum = -5000
        self.thresholdSpin.maximum = 100000
        self.thresholdSpin.singleStep = 10
        self.thresholdSpin.enabled = False
        thresholdRow.addWidget(self.thresholdSpin)
        self.autoButton = qt.QPushButton("Auto (99th percentile)")
        self.autoButton.enabled = False
        self.autoButton.connect("clicked()", self.onAutoThreshold)
        thresholdRow.addWidget(self.autoButton)
        self.layout.addLayout(thresholdRow)

        self.previewButton = qt.QPushButton("3. Generate / update vascular preview")
        self.previewButton.enabled = False
        self.previewButton.connect("clicked()", self.onPreview)
        self.layout.addWidget(self.previewButton)

        self.acceptButton = qt.QPushButton("4. Accept preview and continue")
        self.acceptButton.enabled = False
        self.acceptButton.connect("clicked()", self.onAccept)
        self.layout.addWidget(self.acceptButton)

        note = qt.QLabel("The threshold is a starting estimate, not a validated vessel classifier. Inspect the overlay in axial/coronal/sagittal and 3D views before accepting. No direct patient identifiers are displayed.")
        note.wordWrap = True
        self.layout.addWidget(note)
        self.layout.addStretch(1)

    def onScan(self):
        try:
            self.reports = self.logic.scanInput()
            self.results.setPlainText(self.logic.formatReports(self.reports))
            best = self.logic.best3DSub(self.reports)
            cine = [r for r in self.reports if r.kind == "XA_CINE" and r.valid]
            if best and best.valid:
                self.summaryLabel.text = f"READY: 3D SUB passed ({best.score}/100); {len(cine)} valid cine series."
                self.loadButton.enabled = True
            else:
                self.summaryLabel.text = "NOT READY: no valid 3D subtraction volume."
                self.loadButton.enabled = False
        except Exception as exc:
            self.summaryLabel.text = "ERROR during validation"
            self.results.setPlainText(str(exc))

    def onLoadVolume(self):
        try:
            best = self.logic.best3DSub(self.reports)
            self.volumeNode = self.logic.loadSeries(best.series_uid)
            lo, hi = self.logic.volumeRange(self.volumeNode)
            self.volumeStatus.text = f"Loaded: {self.volumeNode.GetName()} | intensity range {lo:.1f} to {hi:.1f}"
            self.thresholdSpin.minimum = min(-5000, lo)
            self.thresholdSpin.maximum = max(100000, hi)
            self.thresholdSpin.enabled = True
            self.autoButton.enabled = True
            self.previewButton.enabled = True
            self.onAutoThreshold()
            slicer.util.setSliceViewerLayers(background=self.volumeNode, fit=True)
        except Exception as exc:
            slicer.util.errorDisplay(f"Could not load 3D SUB volume:\n{exc}")

    def onAutoThreshold(self):
        try:
            value = self.logic.autoThreshold(self.volumeNode)
            self.thresholdSpin.value = value
            self.volumeStatus.text = self.volumeStatus.text.split(" | suggested threshold")[0] + f" | suggested threshold {value:.1f}"
        except Exception as exc:
            slicer.util.errorDisplay(str(exc))

    def onPreview(self):
        try:
            self.segmentationNode = self.logic.preview(self.volumeNode, self.thresholdSpin.value, self.segmentationNode)
            self.acceptButton.enabled = True
            self.volumeStatus.text = self.volumeStatus.text.split(" | preview")[0] + f" | preview ≥ {self.thresholdSpin.value:.1f}"
            slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
        except Exception as exc:
            slicer.util.errorDisplay(f"Preview failed:\n{exc}")

    def onAccept(self):
        if not self.segmentationNode:
            return
        self.segmentationNode.SetName("DSAFlow_Vessels_Accepted")
        self.acceptButton.enabled = False
        slicer.util.infoDisplay("Preview accepted. Segmentation remains editable in Segment Editor. Next milestone: connected-component cleanup, vascular model generation, and centerline extraction.")


class DSAFlowLogic(ScriptedLoadableModuleLogic):
    def _libs(self):
        module_dir = os.path.dirname(os.path.abspath(__file__))
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
        from DSAFlowLib import dicom_io, segmentation
        return dicom_io, segmentation

    def scanInput(self):
        return self._libs()[0].discover_dsa_series()

    def best3DSub(self, reports):
        candidates = [r for r in reports if r.kind == "3D_SUB"]
        return max(candidates, key=lambda r: (r.valid, r.score, r.file_count), default=None)

    def loadSeries(self, series_uid):
        db = slicer.dicomDatabase
        files = list(db.filesForSeries(series_uid))
        if not files:
            raise RuntimeError("Selected DICOM series contains no files.")
        loaded_node_ids = []
        success = slicer.util.loadVolume(files[0], properties={"singleFile": False}, returnNode=True)
        if isinstance(success, tuple):
            ok, node = success
            if ok and node:
                return node
        # Preferred DICOM route if direct volume loading does not work.
        import DICOMLib
        indexer = DICOMLib.DICOMUtils
        loaded = indexer.loadSeriesByUID([series_uid])
        if loaded:
            for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
                if node.GetAttribute("DICOM.SeriesInstanceUID") == series_uid:
                    return node
        raise RuntimeError("Slicer could not identify the loaded scalar volume for this SeriesInstanceUID.")

    def volumeRange(self, volume_node):
        return self._libs()[1].scalar_range(volume_node)

    def autoThreshold(self, volume_node):
        return self._libs()[1].percentile_threshold(volume_node, 99.0)

    def preview(self, volume_node, lower, segmentation_node=None):
        return self._libs()[1].create_preview(volume_node, lower, None, segmentation_node)

    def formatReports(self, reports):
        if not reports:
            return "No supported DSA series found."
        lines = []
        for r in sorted(reports, key=lambda x: (x.kind, x.description)):
            lines.append(f"[{'PASS' if r.valid else 'REVIEW'}] {r.kind} | {r.description} | {r.score}/100")
            m = r.metadata
            if r.kind == "3D_SUB":
                lines.append(f"  {r.file_count} slices | {m.get('rows')}×{m.get('columns')} | spacing {m.get('pixel_spacing_mm')} mm | slice {m.get('slice_thickness_mm')} mm")
            else:
                lines.append(f"  {m.get('number_of_frames')} frames | {m.get('cine_rate_fps')} fps | angles {m.get('primary_angle_deg')}°/{m.get('secondary_angle_deg')}°")
            for item in r.warnings: lines.append(f"  WARNING: {item}")
            for item in r.failures: lines.append(f"  FAIL: {item}")
            lines.append("")
        return "\n".join(lines)
