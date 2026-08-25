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
        self.parent.helpText = "Guided cerebral DSA segmentation with threshold, ROI vesselness, and seed connectivity."
        self.parent.acknowledgementText = "Research software; not for clinical decision-making."


class DSAFlowWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        super().setup()
        self.logic = DSAFlowLogic()
        self.reports = []
        self.volumeNode = None
        self.segmentationNode = None
        self.roiNode = None
        self.croppedNode = None
        self.vesselnessNode = None
        self.seedNode = None
        self.seedSegmentationNode = None

        intro = qt.QLabel("<b>DSA Flow</b><br>validate → load 3D SUB → threshold baseline → ROI → Frangi vesselness → seed connectivity → 3D review")
        intro.wordWrap = True
        self.layout.addWidget(intro)

        self.scanButton = qt.QPushButton("1. Scan DICOM database")
        self.scanButton.connect("clicked()", self.onScan)
        self.layout.addWidget(self.scanButton)

        self.summaryLabel = qt.QLabel("Status: waiting for scan")
        self.summaryLabel.wordWrap = True
        self.layout.addWidget(self.summaryLabel)

        self.results = qt.QTextEdit(); self.results.readOnly = True; self.results.minimumHeight = 130
        self.layout.addWidget(self.results)

        self.loadButton = qt.QPushButton("2. Load best 3D subtraction volume")
        self.loadButton.enabled = False; self.loadButton.connect("clicked()", self.onLoadVolume)
        self.layout.addWidget(self.loadButton)

        self.volumeStatus = qt.QLabel("3D volume: not loaded"); self.volumeStatus.wordWrap = True
        self.layout.addWidget(self.volumeStatus)

        baselineBox = qt.QGroupBox("3. Baseline threshold (comparison only)")
        baselineLayout = qt.QVBoxLayout(baselineBox)
        thresholdRow = qt.QHBoxLayout()
        thresholdRow.addWidget(qt.QLabel("Lower:"))
        self.thresholdSpin = qt.QDoubleSpinBox(); self.thresholdSpin.decimals = 1; self.thresholdSpin.enabled = False
        thresholdRow.addWidget(self.thresholdSpin)
        thresholdRow.addWidget(qt.QLabel("Upper:"))
        self.upperSpin = qt.QDoubleSpinBox(); self.upperSpin.decimals = 1; self.upperSpin.enabled = False
        thresholdRow.addWidget(self.upperSpin)
        self.autoButton = qt.QPushButton("Auto"); self.autoButton.enabled = False; self.autoButton.connect("clicked()", self.onAutoThreshold)
        thresholdRow.addWidget(self.autoButton)
        baselineLayout.addLayout(thresholdRow)
        self.rawButton = qt.QPushButton("Generate raw threshold preview"); self.rawButton.enabled = False; self.rawButton.connect("clicked()", self.onRawPreview)
        baselineLayout.addWidget(self.rawButton)
        self.layout.addWidget(baselineBox)

        vesselBox = qt.QGroupBox("4. ROI + multiscale vesselness")
        vesselLayout = qt.QVBoxLayout(vesselBox)
        roiRow = qt.QHBoxLayout()
        roiRow.addWidget(qt.QLabel("ROI size (mm):"))
        self.roiSizeSpin = qt.QDoubleSpinBox(); self.roiSizeSpin.minimum = 20; self.roiSizeSpin.maximum = 120; self.roiSizeSpin.value = 50; self.roiSizeSpin.enabled = False
        roiRow.addWidget(self.roiSizeSpin)
        roiRow.addWidget(qt.QLabel("Resample ×:"))
        self.resampleSpin = qt.QDoubleSpinBox(); self.resampleSpin.minimum = 1.0; self.resampleSpin.maximum = 4.0; self.resampleSpin.singleStep = 0.5; self.resampleSpin.value = 2.0; self.resampleSpin.enabled = False
        roiRow.addWidget(self.resampleSpin)
        vesselLayout.addLayout(roiRow)

        self.createROIButton = qt.QPushButton("4A. Create centered ROI — reposition around aneurysm")
        self.createROIButton.enabled = False; self.createROIButton.connect("clicked()", self.onCreateROI)
        vesselLayout.addWidget(self.createROIButton)
        self.cropButton = qt.QPushButton("4B. Crop/resample selected ROI")
        self.cropButton.enabled = False; self.cropButton.connect("clicked()", self.onCropROI)
        vesselLayout.addWidget(self.cropButton)
        self.frangiButton = qt.QPushButton("4C. Run multiscale Frangi vesselness")
        self.frangiButton.enabled = False; self.frangiButton.connect("clicked()", self.onFrangi)
        vesselLayout.addWidget(self.frangiButton)
        self.vesselStatus = qt.QLabel("Vesselness: not generated"); self.vesselStatus.wordWrap = True
        vesselLayout.addWidget(self.vesselStatus)
        self.layout.addWidget(vesselBox)

        seedBox = qt.QGroupBox("5. Seed connectivity — isolate the vascular tree of interest")
        seedLayout = qt.QVBoxLayout(seedBox)
        self.seedButton = qt.QPushButton("5A. Create vessel seed points")
        self.seedButton.enabled = False; self.seedButton.connect("clicked()", self.onCreateSeeds)
        seedLayout.addWidget(self.seedButton)
        seedParams = qt.QHBoxLayout()
        seedParams.addWidget(qt.QLabel("Vesselness threshold:"))
        self.vesselThresholdSpin = qt.QDoubleSpinBox(); self.vesselThresholdSpin.minimum = 0.001; self.vesselThresholdSpin.maximum = 1.0; self.vesselThresholdSpin.decimals = 3; self.vesselThresholdSpin.singleStep = 0.01; self.vesselThresholdSpin.value = 0.12; self.vesselThresholdSpin.enabled = False
        seedParams.addWidget(self.vesselThresholdSpin)
        seedParams.addWidget(qt.QLabel("Min voxels:"))
        self.seedMinSpin = qt.QSpinBox(); self.seedMinSpin.minimum = 1; self.seedMinSpin.maximum = 100000; self.seedMinSpin.value = 30; self.seedMinSpin.enabled = False
        seedParams.addWidget(self.seedMinSpin)
        seedLayout.addLayout(seedParams)
        self.connectButton = qt.QPushButton("5B. Keep only components connected to seeds")
        self.connectButton.enabled = False; self.connectButton.connect("clicked()", self.onSeedConnectivity)
        seedLayout.addWidget(self.connectButton)
        self.seed3DButton = qt.QPushButton("5C. Generate 3D seeded vascular preview")
        self.seed3DButton.enabled = False; self.seed3DButton.connect("clicked()", self.onSeed3D)
        seedLayout.addWidget(self.seed3DButton)
        self.seedStatus = qt.QLabel("Seed connectivity: not generated"); self.seedStatus.wordWrap = True
        seedLayout.addWidget(self.seedStatus)
        self.layout.addWidget(seedBox)

        self.acceptButton = qt.QPushButton("6. Accept seeded vascular segmentation")
        self.acceptButton.enabled = False; self.acceptButton.connect("clicked()", self.onAccept)
        self.layout.addWidget(self.acceptButton)

        note = qt.QLabel(
            "Workflow note: do not use the whole-head threshold surface to judge aneurysm morphology. Position the ROI around the arterial territory/aneurysm, run vesselness, and place seeds inside true vessels (e.g., parent artery and branches). The seed step deliberately rejects structures that are bright but not connected to the selected vascular tree."
        )
        note.wordWrap = True; self.layout.addWidget(note); self.layout.addStretch(1)

    def onScan(self):
        try:
            self.reports = self.logic.scanInput(); self.results.setPlainText(self.logic.formatReports(self.reports))
            best = self.logic.best3DSub(self.reports); cine = [r for r in self.reports if r.kind == "XA_CINE" and r.valid]
            if best and best.valid:
                self.summaryLabel.text = f"READY: 3D SUB passed ({best.score}/100); {len(cine)} valid cine series."
                self.loadButton.enabled = True
            else:
                self.summaryLabel.text = "NOT READY: no valid 3D subtraction volume."
        except Exception as exc:
            self.summaryLabel.text = "ERROR during validation"; self.results.setPlainText(str(exc))

    def onLoadVolume(self):
        try:
            best = self.logic.best3DSub(self.reports); self.volumeNode = self.logic.loadSeries(best.series_uid)
            lo, hi = self.logic.volumeRange(self.volumeNode); dims = self.volumeNode.GetImageData().GetDimensions(); spacing = self.volumeNode.GetSpacing()
            self.volumeStatus.text = f"Loaded 3D SUB | {dims[0]}×{dims[1]}×{dims[2]} | {spacing[0]:.4f}×{spacing[1]:.4f}×{spacing[2]:.4f} mm | intensity {lo:.1f}–{hi:.1f}"
            for w in [self.thresholdSpin, self.upperSpin]: w.minimum = lo; w.maximum = hi; w.enabled = True
            self.upperSpin.value = hi
            for w in [self.autoButton, self.rawButton, self.roiSizeSpin, self.resampleSpin, self.createROIButton]: w.enabled = True
            self.onAutoThreshold(); slicer.util.setSliceViewerLayers(background=self.volumeNode, fit=True)
        except Exception as exc:
            slicer.util.errorDisplay(f"Could not load 3D SUB:\n{exc}")

    def onAutoThreshold(self):
        try:
            self.thresholdSpin.value = self.logic.autoThreshold(self.volumeNode)
        except Exception as exc: slicer.util.errorDisplay(str(exc))

    def onRawPreview(self):
        try:
            self.segmentationNode = self.logic.rawPreview(self.volumeNode, self.thresholdSpin.value, self.upperSpin.value, self.segmentationNode)
            slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
        except Exception as exc: slicer.util.errorDisplay(f"Raw preview failed:\n{exc}")

    def onCreateROI(self):
        try:
            self.roiNode = self.logic.createROI(self.volumeNode, self.roiSizeSpin.value, self.roiNode)
            self.cropButton.enabled = True
            slicer.util.infoDisplay("ROI created. Reposition/resize the magenta ROI around the aneurysm and parent arterial territory, then crop.")
        except Exception as exc: slicer.util.errorDisplay(str(exc))

    def onCropROI(self):
        try:
            self.croppedNode = self.logic.cropROI(self.volumeNode, self.roiNode, self.resampleSpin.value, self.croppedNode)
            dims = self.croppedNode.GetImageData().GetDimensions(); sp = self.croppedNode.GetSpacing()
            self.vesselStatus.text = f"ROI volume ready: {dims[0]}×{dims[1]}×{dims[2]} voxels | spacing {sp[0]:.3f}×{sp[1]:.3f}×{sp[2]:.3f} mm"
            self.frangiButton.enabled = True
            slicer.util.setSliceViewerLayers(background=self.croppedNode, fit=True)
        except Exception as exc: slicer.util.errorDisplay(f"ROI crop failed:\n{exc}")

    def onFrangi(self):
        try:
            self.frangiButton.enabled = False; self.vesselStatus.text = "Running multiscale Hessian/Frangi vesselness…"; slicer.app.processEvents()
            self.vesselnessNode = self.logic.frangi(self.croppedNode)
            self.vesselStatus.text = "Vesselness generated and normalized to 0–1. Review bright tubular structures in slice views."
            self.seedButton.enabled = True; self.vesselThresholdSpin.enabled = True; self.seedMinSpin.enabled = True
            slicer.util.setSliceViewerLayers(background=self.vesselnessNode, fit=True)
        except Exception as exc:
            slicer.util.errorDisplay(f"Frangi vesselness failed:\n{exc}")
        finally:
            self.frangiButton.enabled = True

    def onCreateSeeds(self):
        try:
            self.seedNode = self.logic.createSeeds(self.seedNode); self.connectButton.enabled = True
            slicer.util.infoDisplay("Seed node created. Use the Markups placement tool to place points inside the parent artery and, if useful, distal branches connected to the aneurysm.")
        except Exception as exc: slicer.util.errorDisplay(str(exc))

    def onSeedConnectivity(self):
        try:
            self.seedSegmentationNode, stats = self.logic.seedConnectivity(self.vesselnessNode, self.seedNode, self.vesselThresholdSpin.value, self.seedMinSpin.value, self.seedSegmentationNode)
            self.seedStatus.text = f"Seeded mask: {stats['seeded_components']} connected component(s), {stats['mask_voxels']:,} voxels, vesselness ≥ {stats['threshold']:.3f}."
            self.seed3DButton.enabled = True; self.acceptButton.enabled = True
            slicer.util.setSliceViewerLayers(background=self.croppedNode, fit=True)
        except Exception as exc: slicer.util.errorDisplay(f"Seed connectivity failed:\n{exc}")

    def onSeed3D(self):
        try:
            self.seedSegmentationNode.CreateClosedSurfaceRepresentation()
            d = self.seedSegmentationNode.GetDisplayNode(); d.SetVisibility3D(True); d.SetVisibility2DFill(True)
            slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
        except Exception as exc: slicer.util.errorDisplay(f"Seeded 3D preview failed:\n{exc}")

    def onAccept(self):
        if self.seedSegmentationNode:
            self.seedSegmentationNode.SetName("DSAFlow_Vessels_Accepted")
            self.acceptButton.enabled = False
            slicer.util.infoDisplay("Seed-connected segmentation accepted. Next step: surface optimization, aneurysm/parent-vessel labeling, and centerline extraction.")


class DSAFlowLogic(ScriptedLoadableModuleLogic):
    def _libs(self):
        module_dir = os.path.dirname(os.path.abspath(__file__))
        if module_dir not in sys.path: sys.path.insert(0, module_dir)
        from DSAFlowLib import dicom_io, segmentation, vesselness
        return dicom_io, segmentation, vesselness

    def scanInput(self): return self._libs()[0].discover_dsa_series()
    def best3DSub(self, reports):
        candidates = [r for r in reports if r.kind == "3D_SUB"]
        return max(candidates, key=lambda r: (r.valid, r.score, r.file_count), default=None)

    def loadSeries(self, series_uid):
        db = slicer.dicomDatabase; files = list(db.filesForSeries(series_uid))
        if not files: raise RuntimeError("Selected DICOM series contains no files.")
        for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
            if node.GetAttribute("DICOM.SeriesInstanceUID") == series_uid and node.GetImageData() is not None: return node
        before = {n.GetID() for n in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")}
        from DICOMLib import DICOMUtils; DICOMUtils.loadSeriesByUID([series_uid])
        new = [n for n in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode") if n.GetID() not in before and n.GetImageData() is not None]
        expected = len(files); depth = [n for n in new if n.GetImageData().GetDimensions()[2] == expected]
        if len(depth) == 1: depth[0].SetAttribute("DICOM.SeriesInstanceUID", series_uid); return depth[0]
        if len(new) == 1: new[0].SetAttribute("DICOM.SeriesInstanceUID", series_uid); return new[0]
        raise RuntimeError(f"Could not uniquely identify loaded 3D volume; expected {expected} slices, got {len(new)} new volumes.")

    def volumeRange(self, n): return self._libs()[1].scalar_range(n)
    def autoThreshold(self, n): return self._libs()[1].percentile_threshold(n, 99.0)
    def rawPreview(self, v, lo, hi, s=None): return self._libs()[1].create_preview(v, lo, hi, s)
    def createROI(self, v, size, r=None): return self._libs()[2].create_centered_roi(v, size, r)
    def cropROI(self, v, r, scale, out=None): return self._libs()[2].crop_to_roi(v, r, scale, out)
    def frangi(self, v): return self._libs()[2].frangi_multiscale(v)
    def createSeeds(self, s=None): return self._libs()[2].create_seed_node(s)
    def seedConnectivity(self, v, seeds, thr, minvox, seg=None):
        mask, stats = self._libs()[2].seed_connected_mask(v, seeds, thr, minvox)
        return self._libs()[2].mask_to_segmentation(mask, v, seg), stats

    def formatReports(self, reports):
        if not reports: return "No supported DSA series found."
        lines = []
        for r in sorted(reports, key=lambda x: (x.kind, x.description)):
            lines.append(f"[{'PASS' if r.valid else 'REVIEW'}] {r.kind} | {r.description} | {r.score}/100")
            m = r.metadata
            if r.kind == "3D_SUB": lines.append(f"  {r.file_count} slices | {m.get('rows')}×{m.get('columns')} | spacing {m.get('pixel_spacing_mm')} mm")
            else: lines.append(f"  {m.get('number_of_frames')} frames | {m.get('cine_rate_fps')} fps | angles {m.get('primary_angle_deg')}°/{m.get('secondary_angle_deg')}°")
            for item in r.warnings: lines.append(f"  WARNING: {item}")
            for item in r.failures: lines.append(f"  FAIL: {item}")
            lines.append("")
        return "\n".join(lines)
