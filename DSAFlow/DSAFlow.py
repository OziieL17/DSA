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

        intro = qt.QLabel("<b>DSA Flow</b><br>Guided workflow: validate → load 3D SUB → raw preview → clean preview → 3D preview → accept.")
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
        self.results.minimumHeight = 180
        self.layout.addWidget(self.results)

        self.loadButton = qt.QPushButton("2. Load best 3D subtraction volume")
        self.loadButton.enabled = False
        self.loadButton.connect("clicked()", self.onLoadVolume)
        self.layout.addWidget(self.loadButton)

        self.volumeStatus = qt.QLabel("3D volume: not loaded")
        self.volumeStatus.wordWrap = True
        self.layout.addWidget(self.volumeStatus)

        thresholdRow = qt.QHBoxLayout()
        thresholdRow.addWidget(qt.QLabel("Lower:"))
        self.thresholdSpin = qt.QDoubleSpinBox()
        self.thresholdSpin.decimals = 1
        self.thresholdSpin.minimum = -5000
        self.thresholdSpin.maximum = 100000
        self.thresholdSpin.singleStep = 10
        self.thresholdSpin.enabled = False
        thresholdRow.addWidget(self.thresholdSpin)

        thresholdRow.addWidget(qt.QLabel("Upper:"))
        self.upperSpin = qt.QDoubleSpinBox()
        self.upperSpin.decimals = 1
        self.upperSpin.minimum = -5000
        self.upperSpin.maximum = 100000
        self.upperSpin.singleStep = 100
        self.upperSpin.enabled = False
        thresholdRow.addWidget(self.upperSpin)

        self.autoButton = qt.QPushButton("Auto")
        self.autoButton.enabled = False
        self.autoButton.connect("clicked()", self.onAutoThreshold)
        thresholdRow.addWidget(self.autoButton)
        self.layout.addLayout(thresholdRow)

        self.rawButton = qt.QPushButton("3A. Generate raw threshold preview")
        self.rawButton.enabled = False
        self.rawButton.connect("clicked()", self.onRawPreview)
        self.layout.addWidget(self.rawButton)

        cleanupRow = qt.QHBoxLayout()
        cleanupRow.addWidget(qt.QLabel("Min component voxels:"))
        self.minVoxelSpin = qt.QSpinBox()
        self.minVoxelSpin.minimum = 1
        self.minVoxelSpin.maximum = 1000000
        self.minVoxelSpin.value = 150
        self.minVoxelSpin.enabled = False
        cleanupRow.addWidget(self.minVoxelSpin)
        cleanupRow.addWidget(qt.QLabel("Max components:"))
        self.maxComponentsSpin = qt.QSpinBox()
        self.maxComponentsSpin.minimum = 1
        self.maxComponentsSpin.maximum = 500
        self.maxComponentsSpin.value = 40
        self.maxComponentsSpin.enabled = False
        cleanupRow.addWidget(self.maxComponentsSpin)
        self.layout.addLayout(cleanupRow)

        self.cleanButton = qt.QPushButton("3B. Clean connected components")
        self.cleanButton.enabled = False
        self.cleanButton.connect("clicked()", self.onCleanPreview)
        self.layout.addWidget(self.cleanButton)

        modeRow = qt.QHBoxLayout()
        self.showRawButton = qt.QPushButton("Show raw")
        self.showRawButton.enabled = False
        self.showRawButton.connect("clicked()", lambda: self.onMode("raw"))
        modeRow.addWidget(self.showRawButton)
        self.showCleanButton = qt.QPushButton("Show clean")
        self.showCleanButton.enabled = False
        self.showCleanButton.connect("clicked()", lambda: self.onMode("clean"))
        modeRow.addWidget(self.showCleanButton)
        self.layout.addLayout(modeRow)

        self.statsLabel = qt.QLabel("Cleanup statistics: not generated")
        self.statsLabel.wordWrap = True
        self.layout.addWidget(self.statsLabel)

        self.surfaceButton = qt.QPushButton("3C. Generate controlled 3D vascular preview")
        self.surfaceButton.enabled = False
        self.surfaceButton.connect("clicked()", self.on3DPreview)
        self.layout.addWidget(self.surfaceButton)

        self.acceptButton = qt.QPushButton("4. Accept clean segmentation")
        self.acceptButton.enabled = False
        self.acceptButton.connect("clicked()", self.onAccept)
        self.layout.addWidget(self.acceptButton)

        note = qt.QLabel(
            "Raw preview shows everything passing the intensity threshold. Clean preview removes small disconnected islands and retains only the largest connected vascular components. "
            "The first true 3D surface is generated only after cleanup. If this still does not resemble the vascular tree you expect, do not accept it; threshold and cleanup remain editable."
        )
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
                f"Loaded full 3D SUB: {self.volumeNode.GetName()} | dimensions {dims[0]}×{dims[1]}×{dims[2]} | "
                f"spacing {spacing[0]:.4f}×{spacing[1]:.4f}×{spacing[2]:.4f} mm | intensity {lo:.1f} to {hi:.1f}"
            )
            self.thresholdSpin.minimum = lo
            self.thresholdSpin.maximum = hi
            self.upperSpin.minimum = lo
            self.upperSpin.maximum = hi
            self.upperSpin.value = hi
            for w in [self.thresholdSpin, self.upperSpin, self.autoButton, self.rawButton, self.minVoxelSpin, self.maxComponentsSpin]:
                w.enabled = True
            self.onAutoThreshold()
            slicer.util.setSliceViewerLayers(background=self.volumeNode, fit=True)
        except Exception as exc:
            slicer.util.errorDisplay(f"Could not load full 3D SUB series:\n{exc}")

    def onAutoThreshold(self):
        try:
            value = self.logic.autoThreshold(self.volumeNode)
            self.thresholdSpin.value = value
            self.upperSpin.value = self.logic.volumeRange(self.volumeNode)[1]
            self.volumeStatus.text = self.volumeStatus.text.split(" | suggested threshold")[0] + f" | suggested threshold {value:.1f}"
        except Exception as exc:
            slicer.util.errorDisplay(str(exc))

    def onRawPreview(self):
        try:
            self.segmentationNode = self.logic.rawPreview(self.volumeNode, self.thresholdSpin.value, self.upperSpin.value, self.segmentationNode)
            self.cleanButton.enabled = True
            self.showRawButton.enabled = True
            self.volumeStatus.text = self.volumeStatus.text.split(" | preview")[0] + f" | raw preview {self.thresholdSpin.value:.1f}–{self.upperSpin.value:.1f}"
            slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
        except Exception as exc:
            slicer.util.errorDisplay(f"Raw preview failed:\n{exc}")

    def onCleanPreview(self):
        try:
            self.segmentationNode, stats = self.logic.cleanPreview(
                self.volumeNode,
                self.thresholdSpin.value,
                self.upperSpin.value,
                self.minVoxelSpin.value,
                self.maxComponentsSpin.value,
                self.segmentationNode,
            )
            self.showRawButton.enabled = True
            self.showCleanButton.enabled = True
            self.surfaceButton.enabled = True
            self.acceptButton.enabled = True
            self.statsLabel.text = (
                f"Cleanup statistics: {stats['components_total']} components detected; {stats['components_retained']} retained. "
                f"Voxels {stats['raw_voxels']:,} → {stats['clean_voxels']:,} ({100*stats['retained_fraction']:.1f}% retained). "
                f"Largest component: {stats['largest_component_voxels']:,} voxels."
            )
            self.logic.setMode(self.segmentationNode, "clean")
        except Exception as exc:
            slicer.util.errorDisplay(f"Cleanup failed:\n{exc}")

    def onMode(self, mode):
        self.logic.setMode(self.segmentationNode, mode)

    def on3DPreview(self):
        try:
            self.logic.create3D(self.segmentationNode)
            slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
            self.statsLabel.text += " | 3D surface generated from CleanVessels."
        except Exception as exc:
            slicer.util.errorDisplay(f"3D preview failed:\n{exc}")

    def onAccept(self):
        if not self.segmentationNode:
            return
        self.segmentationNode.SetName("DSAFlow_Vessels_Accepted")
        self.acceptButton.enabled = False
        slicer.util.infoDisplay("Clean segmentation accepted. Next milestone: vascular model optimization and centerline extraction.")


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
        expected_slices = len(files)
        depth_matches = [n for n in candidates if n.GetImageData().GetDimensions()[2] == expected_slices]
        if len(depth_matches) == 1:
            depth_matches[0].SetAttribute("DICOM.SeriesInstanceUID", series_uid)
            return depth_matches[0]
        if len(candidates) == 1:
            candidates[0].SetAttribute("DICOM.SeriesInstanceUID", series_uid)
            return candidates[0]
        raise RuntimeError(f"Could not uniquely identify loaded 3D volume; expected {expected_slices} slices, got {len(candidates)} new scalar volumes.")

    def volumeRange(self, volume_node):
        return self._libs()[1].scalar_range(volume_node)

    def autoThreshold(self, volume_node):
        return self._libs()[1].percentile_threshold(volume_node, 99.0)

    def rawPreview(self, volume_node, lower, upper, segmentation_node=None):
        return self._libs()[1].create_preview(volume_node, lower, upper, segmentation_node)

    def cleanPreview(self, volume_node, lower, upper, min_voxels, max_components, segmentation_node=None):
        return self._libs()[1].create_clean_preview(volume_node, lower, upper, min_voxels, max_components, segmentation_node)

    def setMode(self, segmentation_node, mode):
        return self._libs()[1].set_preview_mode(segmentation_node, mode)

    def create3D(self, segmentation_node):
        return self._libs()[1].create_controlled_3d_surface(segmentation_node)

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
