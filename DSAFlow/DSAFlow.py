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

        note = qt.QLabel("The 3DANGIO SUB series is already a vendor-generated subtraction reconstruction; DSAFlow does not subtract Fill-Mask again at this step. Preview is shown in 2D first to avoid an unnecessary full-volume surface extraction. No direct patient identifiers are displayed.")
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
            dims = self.volumeNode.GetImageData().GetDimensions()
            spacing = self.volumeNode.GetSpacing()
            self.volumeStatus.text = (
                f"Loaded full 3D SUB: {self.volumeNode.GetName()} | "
                f"dimensions {dims[0]}×{dims[1]}×{dims[2]} | "
                f"spacing {spacing[0]:.4f}×{spacing[1]:.4f}×{spacing[2]:.4f} mm | "
                f"intensity {lo:.1f} to {hi:.1f}"
            )
            self.thresholdSpin.minimum = min(-5000, lo)
            self.thresholdSpin.maximum = max(100000, hi)
            self.thresholdSpin.enabled = True
            self.autoButton.enabled = True
            self.previewButton.enabled = True
            self.onAutoThreshold()
            slicer.util.setSliceViewerLayers(background=self.volumeNode, fit=True)
        except Exception as exc:
            slicer.util.errorDisplay(f"Could not load full 3D SUB series:\n{exc}")

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
            self.volumeStatus.text = self.volumeStatus.text.split(" | preview")[0] + f" | 2D preview ≥ {self.thresholdSpin.value:.1f}"
            slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
        except Exception as exc:
            slicer.util.errorDisplay(f"Preview failed:\n{exc}")

    def onAccept(self):
        if not self.segmentationNode:
            return
        self.segmentationNode.SetName("DSAFlow_Vessels_Accepted")
        self.acceptButton.enabled = False
        slicer.util.infoDisplay("Preview accepted. Next milestone: crop/connected-component cleanup, then controlled 3D surface generation and centerline extraction.")


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
        """Load the complete DICOM series through Slicer's DICOM plugin machinery.

        Do not call slicer.util.loadVolume on the first DICOM file: that route can
        load only one slice or invoke a generic ITK reader and lose series geometry.
        """
        db = slicer.dicomDatabase
        files = list(db.filesForSeries(series_uid))
        if not files:
            raise RuntimeError("Selected DICOM series contains no files.")

        # Reuse an already-loaded matching volume when possible.
        for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
            uid = node.GetAttribute("DICOM.SeriesInstanceUID")
            if uid == series_uid and node.GetImageData() is not None:
                return node

        before_ids = {node.GetID() for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")}

        from DICOMLib import DICOMUtils
        DICOMUtils.loadSeriesByUID([series_uid])

        candidates = []
        for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
            if node.GetID() in before_ids or node.GetImageData() is None:
                continue
            uid = node.GetAttribute("DICOM.SeriesInstanceUID")
            if uid == series_uid:
                return node
            candidates.append(node)

        # Some DICOM plugins do not propagate SeriesInstanceUID to the MRML node.
        # In that case select the newly-loaded scalar volume with the expected depth.
        expected_slices = len(files)
        depth_matches = []
        for node in candidates:
            dims = node.GetImageData().GetDimensions()
            if dims[2] == expected_slices:
                depth_matches.append(node)
        if len(depth_matches) == 1:
            depth_matches[0].SetAttribute("DICOM.SeriesInstanceUID", series_uid)
            return depth_matches[0]

        if len(candidates) == 1:
            candidates[0].SetAttribute("DICOM.SeriesInstanceUID", series_uid)
            return candidates[0]

        raise RuntimeError(
            f"DICOM loader ran, but DSAFlow could not uniquely identify the 3D volume. "
            f"Expected {expected_slices} slices; newly loaded scalar volumes: {len(candidates)}."
        )

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
