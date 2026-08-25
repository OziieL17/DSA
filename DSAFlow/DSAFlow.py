"""3D Slicer scripted module entry point for DSAFlow.

Initial milestone: DICOM DSA -> preprocessing -> segmentation -> centerlines -> export.
"""

try:
    import slicer
    from slicer.ScriptedLoadableModule import (
        ScriptedLoadableModule,
        ScriptedLoadableModuleWidget,
        ScriptedLoadableModuleLogic,
    )
except ImportError:  # Allows static inspection outside Slicer.
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
        self.parent.helpText = "Research pipeline for cerebral DSA segmentation and flow analysis."
        self.parent.acknowledgementText = "Research software; not for clinical decision-making."


class DSAFlowWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        super().setup()
        # UI will be implemented after the processing API is stable.
        if slicer:
            self.layout.addStretch(1)


class DSAFlowLogic(ScriptedLoadableModuleLogic):
    """Coordinates reusable processing functions exposed by DSAFlowLib."""

    pass
