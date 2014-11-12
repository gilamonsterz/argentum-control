#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Argentum Control GUI

author: Michael Shiel
author: Trent Waddington
"""

import sys
import os
from PyQt4 import QtGui, QtCore

from serial.tools.list_ports import comports
from ArgentumPrinterController import ArgentumPrinterController
from PrintView import PrintView
from avrdude import avrdude

import pickle

from imageproc import ImageProcessor

from Alchemist import OptionsDialog, CommandLineEdit, ServoCalibrationDialog

import esky
from setup import VERSION
from firmware_updater import update_firmware_list, get_available_firmware, update_local_firmware

import subprocess
from multiprocessing import Process

def myrun(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout = []
    while True:
        line = p.stdout.readline()
        stdout.append(line)
        print(line)
        if line == '' and p.poll() != None:
            break
    return ''.join(stdout)

default_options = {
    'horizontal_offset': 726,
    'vertical_offset': 0,
    'print_overlap': 41
}

def load_options():
    try:
        options_file = open('argentum.pickle', 'rb')

    except:
        print('No existing options file, using defaults.')

        return default_options

    return pickle.load(options_file)

def save_options(options):
    try:
        options_file = open('argentum.pickle', 'wb')
    except:
        print('Unable to open options file for writing.')

    pickle.dump(options, options_file)

class Argentum(QtGui.QMainWindow):
    def __init__(self):
        super(Argentum, self).__init__()

        #v = Process(target=updater, args=('http://files.cartesianco.com',))
        #v.start()

        self.printer = ArgentumPrinterController()
        self.programmer = None

        self.paused = False
        self.autoConnect = True

        self.XStepSize = 150
        self.YStepSize = 200

        self.options = load_options()
        save_options(self.options)

        #print('Loaded options: {}'.format(self.options))

        self.initUI()

        self.appendOutput('Argentum Control, Version {}'.format(VERSION))

        if hasattr(sys, "frozen"):
            try:
                app = esky.Esky(sys.executable, 'http://files.cartesianco.com')

                new_version = app.find_update()

                if new_version:
                    self.appendOutput('Update available! Select update from the Utilities menu to upgrade. [{} -> {}]'
                        .format(app.active_version, new_version))

                    self.statusBar().showMessage('Update available!')

            except Exception as e:
                self.appendOutput('Update exception.')
                self.appendOutput(str(e))

                pass
        else:
            self.appendOutput('Update available! Select update from the Utilities menu to upgrade. [{} -> {}]'
                .format('0.0.6', '0.0.7'))
            #pass
            #self.appendOutput('Not packaged - no automatic update support.')

        update_firmware_list()

        update_local_firmware()

        available_firmware = get_available_firmware()

        self.appendOutput('Available firmware versions:')

        for firmware in available_firmware:
            self.appendOutput(firmware['version'])

        # Make a directory where we can place processed images
        docsDir = str(QtGui.QDesktopServices.storageLocation(QtGui.QDesktopServices.DocumentsLocation))
        self.filesDir = os.path.join(docsDir, 'Argentum')
        if not os.path.isdir(self.filesDir):
            os.mkdir(self.filesDir)

    def initUI(self):
        # Create the console
        self.consoleWidget = QtGui.QWidget(self)

        # First Row
        connectionRow = QtGui.QHBoxLayout()

        portLabel = QtGui.QLabel("Ports:")
        self.portListCombo = QtGui.QComboBox(self)
        self.connectButton = QtGui.QPushButton("Connect")

        self.connectButton.clicked.connect(self.connectButtonPushed)

        self.updatePortListTimer = QtCore.QTimer()
        QtCore.QObject.connect(self.updatePortListTimer, QtCore.SIGNAL("timeout()"), self.updatePortList)
        self.updatePortListTimer.start(1000)

        self.portListCombo.setSizePolicy(QtGui.QSizePolicy.Expanding,
                         QtGui.QSizePolicy.Fixed)
        self.portListCombo.setSizeAdjustPolicy(QtGui.QComboBox.AdjustToContents)

        connectionRow.addWidget(portLabel)
        connectionRow.addWidget(self.portListCombo)
        connectionRow.addWidget(self.connectButton)

        # Command Row

        commandRow = QtGui.QHBoxLayout()

        commandLabel = QtGui.QLabel("Command:")
        self.commandField = CommandLineEdit(self) #QtGui.QLineEdit(self)
        self.commandSendButton = QtGui.QPushButton("Send")

        self.commandSendButton.clicked.connect(self.sendButtonPushed)
        self.commandField.connect(self.commandField, QtCore.SIGNAL("enterPressed"), self.sendButtonPushed)

        self.commandField.setSizePolicy(QtGui.QSizePolicy.Expanding,
                         QtGui.QSizePolicy.Fixed)

        commandRow.addWidget(commandLabel)
        commandRow.addWidget(self.commandField)
        commandRow.addWidget(self.commandSendButton)

        # Output Text Window
        self.outputView = QtGui.QTextEdit()

        self.outputView.setReadOnly(True)

        self.outputView.setSizePolicy(QtGui.QSizePolicy.Minimum,
                         QtGui.QSizePolicy.Expanding)

        # Jog Frame

        jogControlsGrid = QtGui.QGridLayout()

        self.upButton = QtGui.QPushButton('^')
        self.downButton = QtGui.QPushButton('v')
        self.leftButton = QtGui.QPushButton('<')
        self.rightButton = QtGui.QPushButton('>')

        self.makeButtonRepeatable(self.upButton)
        self.makeButtonRepeatable(self.downButton)
        self.makeButtonRepeatable(self.leftButton)
        self.makeButtonRepeatable(self.rightButton)

        self.upButton.clicked.connect(self.incrementY)
        self.downButton.clicked.connect(self.decrementY)
        self.leftButton.clicked.connect(self.decrementX)
        self.rightButton.clicked.connect(self.incrementX)

        jogControlsGrid.addWidget(self.upButton, 0, 1)
        jogControlsGrid.addWidget(self.leftButton, 1, 0)
        jogControlsGrid.addWidget(self.rightButton, 1, 2)
        jogControlsGrid.addWidget(self.downButton, 2, 1)

        # Main Controls

        controlRow = QtGui.QHBoxLayout()

        self.printButton = QtGui.QPushButton('Print')
        self.pauseButton = QtGui.QPushButton('Pause')
        self.stopButton = QtGui.QPushButton('Stop')
        self.homeButton = QtGui.QPushButton('Home')
        self.processImageButton = QtGui.QPushButton('Process Image')

        self.printButton.clicked.connect(self.printButtonPushed)
        self.pauseButton.clicked.connect(self.pauseButtonPushed)
        self.stopButton.clicked.connect(self.stopButtonPushed)
        self.homeButton.clicked.connect(self.homeButtonPushed)
        self.processImageButton.clicked.connect(self.processImageButtonPushed)

        controlRow.addWidget(self.printButton)
        controlRow.addWidget(self.pauseButton)
        controlRow.addWidget(self.stopButton)
        controlRow.addWidget(self.homeButton)
        controlRow.addWidget(self.processImageButton)

        # Main Vertical Layout

        verticalLayout = QtGui.QVBoxLayout()
        verticalLayout.addLayout(connectionRow)
        verticalLayout.addLayout(commandRow)
        verticalLayout.addWidget(self.outputView)
        verticalLayout.addLayout(jogControlsGrid)
        verticalLayout.addLayout(controlRow)
        self.consoleWidget.setLayout(verticalLayout)

        # Menu Bar Stuff

        self.flashAction = QtGui.QAction('&Flash Arduino', self)
        self.flashAction.triggered.connect(self.flashActionTriggered)
        self.flashAction.setEnabled(False)

        self.optionsAction = QtGui.QAction('Processing &Options', self)
        self.optionsAction.triggered.connect(self.optionsActionTriggered)
        #self.optionsAction.setEnabled(False)

        self.servoCalibrationAction = QtGui.QAction('Servo Calibration', self)
        self.servoCalibrationAction.triggered.connect(self.servoCalibrationActionTriggered)

        self.updateAction = QtGui.QAction('&Update', self)
        self.updateAction.triggered.connect(self.updateActionTriggered)

        menubar = self.menuBar()
        fileMenu = menubar.addMenu('Utilities')
        fileMenu.addAction(self.flashAction)
        fileMenu.addAction(self.optionsAction)
        fileMenu.addAction(self.updateAction)
        fileMenu.addAction(self.servoCalibrationAction)

        self.statusBar().showMessage('Looking for printer...')

        self.disableAllButtonsExceptConnect()
        
        # Create the Print tab
        self.printWidget = QtGui.QWidget(self)
        horizontalLayout = QtGui.QHBoxLayout()
        self.printView = PrintView()
        horizontalLayout.addWidget(self.printView)
        self.printWidget.setLayout(horizontalLayout)

        # Main Window Setup
        self.tabWidget = QtGui.QTabWidget(self)
        self.tabWidget.setTabPosition(QtGui.QTabWidget.South)
        self.tabWidget.addTab(self.printWidget, "Printer")
        self.tabWidget.addTab(self.consoleWidget, "Console") # always last
        self.setCentralWidget(self.tabWidget)

        self.setGeometry(300, 300, 1000, 800)
        self.setWindowTitle('Argentum Control')
        self.show()

    def makeButtonRepeatable(self, button):
        button.setAutoRepeat(True)
        button.setAutoRepeatDelay(100)
        button.setAutoRepeatInterval(80)

    def processImage(self):
        ip = ImageProcessor(
            horizontal_offset=int(self.options['horizontal_offset']),
            vertical_offset=int(self.options['vertical_offset']),
            overlap=int(self.options['print_overlap'])
        )

        inputFileName = QtGui.QFileDialog.getOpenFileName(self, 'Select an image to process', '~')

        inputFileName = str(inputFileName)

        if inputFileName:
            self.appendOutput('Processing Image ' + inputFileName)
            baseName = os.path.basename(inputFileName)
            if baseName.find('.') != -1:
                baseName = baseName[:baseName.find('.')]
            baseName = baseName + '.hex'
            outputFileName = os.path.join(self.filesDir, baseName)
            self.appendOutput('Writing to ' + outputFileName)
            ip.sliceImage(inputFileName, outputFileName, progressFunc=self.progressFunc)

    def progressFunc(self, y, max_y):
        self.appendOutput('{} out of {}.'.format(y, max_y))

    def appendOutput(self, output):
        self.outputView.append(output)
        # Allow the gui to update during long processing
        QtGui.QApplication.processEvents()

    def monitor(self):
        if self.printer.connected and self.printer.serialDevice.inWaiting():

            data = self.printer.serialDevice.read(1)              # read one, blocking

            n = self.printer.serialDevice.inWaiting()             # look if there is more
            if n:
                data = data + self.printer.serialDevice.read(n)   # and get as much as possible

            if data:
                self.appendOutput(data.decode('utf-8'))

        QtCore.QTimer.singleShot(10, self.monitor)

    ### Button Functions ###

    def servoCalibrationActionTriggered(self):
        optionsDialog = ServoCalibrationDialog(self, None)
        optionsDialog.exec_()

    def updateActionTriggered(self):
        reply = QtGui.QMessageBox.question(self, 'Message',
            'But are you sure?', QtGui.QMessageBox.Yes |
            QtGui.QMessageBox.No, QtGui.QMessageBox.Yes)

        if reply == QtGui.QMessageBox.Yes:
            self.app.auto_update()
        else:
            self.appendOutput('Crisis Averted!')

    def enableAllButtons(self, enabled=True):
        self.connectButton.setEnabled(enabled)
        self.commandSendButton.setEnabled(enabled)
        self.commandField.setEnabled(enabled)
        self.upButton.setEnabled(enabled)
        self.downButton.setEnabled(enabled)
        self.leftButton.setEnabled(enabled)
        self.rightButton.setEnabled(enabled)
        self.printButton.setEnabled(enabled)
        self.pauseButton.setEnabled(enabled)
        self.stopButton.setEnabled(enabled)
        self.homeButton.setEnabled(enabled)
        self.processImageButton.setEnabled(enabled)
        
    def disableAllButtons(self):
        self.enableAllButtons(False)

    def disableAllButtonsExceptConnect(self):
        self.disableAllButtons()
        self.connectButton.setEnabled(True)

    def flashActionTriggered(self):
        if self.programmer != None:
            return

        firmwareFileName = QtGui.QFileDialog.getOpenFileName(self, 'Firmware File', '~')
        firmwareFileName = str(firmwareFileName)

        if firmwareFileName:
            self.disableAllButtons()
            self.printer.disconnect()

            self.appendOutput('Flashing {} with {}...'.format(self.printer.port, firmwareFileName))

            self.programmer = avrdude(port=self.printer.port)
            if self.programmer.flashFile(firmwareFileName):
                self.pollFlashingTimer = QtCore.QTimer()
                QtCore.QObject.connect(self.pollFlashingTimer, QtCore.SIGNAL("timeout()"), self.pollFlashing)
                self.pollFlashingTimer.start(1000)
            else:
                self.appendOutput("Can't flash for some reason.")
                self.appendOutput("")
                self.printer.connect()
                self.enableAllButtons()

    def pollFlashing(self):
        if self.programmer.done():
            self.appendOutput('Flashing completed.')
            self.appendOutput("")
            self.pollFlashingTimer.stop()
            self.pollFlashingTimer = None
            self.programmer = None

            self.printer.connect()
            self.enableAllButtons()

    def optionsActionTriggered(self):
        """options = {
            'stepSizeX': 120,
            'stepSizeY': 120,
            'xAxis':    '',
            'yAxis':    ''
        }"""

        optionsDialog = OptionsDialog(self, options=self.options)
        optionsDialog.exec_()

    def enableConnectionSpecificControls(self, enabled):
        self.flashAction.setEnabled(enabled)
        #self.optionsAction.setEnabled(enabled)

        self.portListCombo.setEnabled(not enabled)

        self.monitor()

    def connectButtonPushed(self):
        if(self.printer.connected):
            self.printer.disconnect()

            self.connectButton.setText('Connect')

            self.enableConnectionSpecificControls(False)
            self.disableAllButtonsExceptConnect()
            self.statusBar().showMessage('Disconnected from printer.')
        else:
            port = str(self.portListCombo.currentText())

            if self.printer.connect(port=port):
                self.connectButton.setText('Disconnect')

                self.enableAllButtons()
                self.enableConnectionSpecificControls(True)
                self.statusBar().showMessage('Connected.')
            else:
                QtGui.QMessageBox.information(self, "Cannot connect to printer", self.printer.lastError)
        self.updatePortList()

    def updatePortList(self):
        curPort = str(self.portListCombo.currentText())
    
        self.portListCombo.clear()

        portList = []
        for port in comports():
            if port[2].find("2341:0042") != -1:
                portList.append(port)

        for port in portList:
            self.portListCombo.addItem(port[0])

        if self.portListCombo.count() == 0:
            self.statusBar().showMessage('No printer connected. Connect your printer.')
        else:
            if curPort == "" or self.portListCombo.findText(curPort) == -1:
                if self.portListCombo.count() == 1:
                    curPort = self.portListCombo.itemText(0)
                else:
                    self.statusBar().showMessage('Multiple printers connected. Please select one.')
                    self.tabWidget.setCurrentWidget(self.consoleWidget)

        if curPort != "":
            idx = self.portListCombo.findText(curPort)
            if idx == -1:
                if self.printer.connected:
                    self.connectButtonPushed()
            else:
                self.portListCombo.setCurrentIndex(idx)
                if self.autoConnect and not self.printer.connected:
                    self.autoConnect = False
                    self.connectButtonPushed()
                    if self.printer.connected:
                        self.tabWidget.setCurrentWidget(self.printWidget)
    
    def processImageButtonPushed(self):
        self.processImage()

    ### Command Functions ###

    def printButtonPushed(self):
        self.sendPrintCommand()

    def pauseButtonPushed(self):
        if(self.paused):
            self.paused = False
            self.pauseButton.setText('Pause')
            self.sendResumeCommand()
        else:
            self.paused = True
            self.pauseButton.setText('Resume')
            self.sendPauseCommand()

    def stopButtonPushed(self):
        self.sendStopCommand()

    def homeButtonPushed(self):
        self.printer.move(0, 0)

    def sendButtonPushed(self):
        command = str(self.commandField.text())

        self.commandField.submit_command()

        self.printer.command(command)

    def sendPrintCommand(self):
        self.printer.start()

    def sendPauseCommand(self):
        self.printer.pause()

    def sendResumeCommand(self):
        self.printer.resume()

    def sendStopCommand(self):
        self.printer.stop()

    def sendMovementCommand(self, x, y):
        self.printer.move(x, y)

    def incrementX(self):
        self.sendMovementCommand(self.XStepSize, None)

    def incrementY(self):
        self.sendMovementCommand(None, self.YStepSize)

    def decrementX(self):
        self.sendMovementCommand(-self.XStepSize, None)

    def decrementY(self):
        self.sendMovementCommand(None, -self.YStepSize)

    # This function is for future movement functionality (continuous movement)
    def handleClicked(self):
        if self.isDown():
            if self._state == 0:
                self._state = 1
                self.setAutoRepeatInterval(50)
                print('press')
            else:
                print('repeat')
        elif self._state == 1:
            self._state = 0
            self.setAutoRepeatInterval(1000)
            #print 'release'
        #else:
            #print 'click'

    def updateOptions(self, val):
        self.options = val
        save_options(self.options)

        print('New options values: {}'.format(self.options))

def main():
    app = QtGui.QApplication(sys.argv)
    app.setOrganizationName("CartesianCo")
    app.setOrganizationDomain("cartesianco.com")
    app.setApplicationName("ArgentumControl")
    app_icon = QtGui.QIcon()
    app_icon.addFile('Icon.ico', QtCore.QSize(16,16))
    app_icon.addFile('Icon.ico', QtCore.QSize(24,24))
    app_icon.addFile('Icon.ico', QtCore.QSize(32,32))
    app_icon.addFile('Icon.ico', QtCore.QSize(48,48))
    app_icon.addFile('Icon.ico', QtCore.QSize(256,256))
    app.setWindowIcon(app_icon)
    ex = Argentum()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
