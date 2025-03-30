"""
This packages contains the various qt designer plugins
"""
# Commented out Qt Designer plugins as they're not needed for runtime and may cause issues
# with PySide6 if QtDesigner is not available

# from qtpy import QtDesigner  # Comment this out as it's not needed for normal operation

class WidgetPlugin:  # Removed QtDesigner dependency
    """
    Base class for writing a designer plugins.

    To write a plugin, inherit from this class and define implement at least:

        - klass()
        - objectName()
    """

    def __init__(self, parent=None):
        # super(WidgetPlugin, self).__init__(parent=parent)  # Removed QtDesigner dependency
        self.initialized = False
        # print(self.name(), self.includeFile(), self.objectName())  # Remove debug print

    def klass(self):
        """
        Returns the classname of the widget
        """
        raise NotImplementedError()

    def initialize(self, form_editor):
        self.initialized = True

    def isInitialized(self):
        return self.initialized

    def isContainer(self):
        return False

    def icon(self):
        return None

    def domXml(self):
        return ('<widget class="%s" name="%s">\n</widget>\n' %
                (self.name(), self.objectName()))

    def group(self):
        return 'pyQode'

    def objectName(self):
        return self.name()

    def includeFile(self):
        return self.klass().__module__

    def name(self):
        return self.klass().__name__

    def toolTip(self):
        return ''

    def whatsThis(self):
        return ''

    def createWidget(self, parent):
        return self.klass()(parent)
