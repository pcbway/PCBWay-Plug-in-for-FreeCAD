#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2022 Yorik van Havre <yorik@uncreated.net>              *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

"""
PCBWay Macro for FreeCAD

https://pcbway.com

This macro sends the currently selected object to the PCBWay website
to get an instant quote for manufacturing. After the object is sent,
a page will be opened on the PCBWay website to allow the user to adjust
details and options.
"""

# code inspired / borrowed from:
# KiCAD PcbWay plugin: https://github.com/pcbway/PCBWay-Plug-in-for-Kicad/blob/main/plugins/thread.py
# urllib-based upload: http://pymotw.com/2/urllib2/#uploading-files
# mime stuff: https://stackoverflow.com/questions/27099290/where-is-mimetools-choose-boundary-function-in-python3#27174474

import tempfile
import os
import FreeCAD
import FreeCADGui
import json
import webbrowser
import urllib.request
import urllib.parse
import email.generator
import itertools


pcb_url = "https://www.pcbway.com/common/freecadupfile"


def msg(message):

    """prints a message where appropriate"""

    FreeCAD.Console.PrintError(message+"\n")
    if FreeCAD.GuiUp:
        from PySide import QtGui
        reply = QtGui.QMessageBox.critical(None,"PCBWay export",message)


class MultiPartData(object):

    """Gathers data and files to be sent via HTTP POST"""

    def __init__(self):
        self.form_fields = []
        self.files = []
        self.boundary = email.generator._make_boundary()
        self.add_field("Unit","Millimeter") #FreeCAD's boundboxes are always in mm
        return

    def get_content_type(self):
        return 'multipart/form-data; boundary=%s' % self.boundary

    def add_field(self, name, value):
        """Add a simple field to the form data."""
        self.form_fields.append((name, str(value)))
        return

    def add_file(self, fieldname, filename, fileHandle):
        """Add a file to be uploaded."""
        body = fileHandle.read()
        self.files.append((fieldname, filename, "application/STEP", body))
        return

    def get_bytes(self):
        """Return a string representing the form data, including attached files."""
        parts = []
        part_boundary = '--' + self.boundary
        parts.extend([part_boundary,'Content-Disposition: form-data; name="%s"' % name,'',value] for name, value in self.form_fields)
        parts.extend([part_boundary,'Content-Disposition: file; name="%s"; filename="%s"' % (field_name, filename),
                                    'Content-Type: %s' % content_type,'',body] for field_name, filename, content_type, body in self.files)
        flattened = list(itertools.chain(*parts))
        flattened.append('--' + self.boundary + '--')
        flattened.append('')
        return bytes('\r\n'.join(flattened),'utf8')


def main():

    # validity tests
    if not FreeCAD.GuiUp:
        return
    if not FreeCAD.ActiveDocument:
        msg("There is no opened document. Please open or create a document containing objects before running this macro.")
        return
    # get the selected object, or the only visible body or object if nothing is selected
    selection = FreeCADGui.Selection.getSelection()
    if not selection:
        visibles = [obj for obj in FreeCAD.ActiveDocument.Objects if obj.ViewObject.Visibility and hasattr(obj,"Shape")]
        if len(visibles) == 1:
            shape = visibles[0].Shape
        else:
            bodies = [obj for obj in visibles if obj.isDerivedFrom("PartDesign::Body")]
            if len(bodies) == 1:
                shape = bodies[0].Shape
            else:
                msg("No object is selected. Please select one object before running this macro.")
                return
    elif len(selection) > 1:
        msg("More than one object is selected. Please select only one object before running this macro.")
        return
    else:
        shape = getattr(selection[0],"Shape",None)
        if (not shape) or (not hasattr(shape,"isNull")) or shape.isNull():
            msg("The selected object has no shape. Please select an object with a shape before running this macro.")
            return

    # offer to add the macro as a button on first run
    # not working yet!
    # prefs = FreeCAD.ParamGet("User parameter:Plugins/PCBWay")
    # if prefs.GetBool("FirstTime",True):
    #    prefs.SetBool("FirstTime",False)
    #    from PySide import QtGui
    #    reply = QtGui.QMessageBox.question(None, "Install macro?",
    #        "This is the first time you are launching the PCBWay macro. Do you wish to add a toolbar button for it?",
    #        QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No)
    #    if reply == QtGui.QMessageBox.Yes:
    #        icon = "https://github.com/pcbway/PCBWay-Plug-in-for-Kicad/raw/main/resources/icon.png"
    #        u = urllib.request.urlopen(icon)
    #        idata = u.read()
    #        u.close()
    #        idir = os.path.join(FreeCAD.getUserAppDataDir(),"icons")
    #        os.makedirs(idir,exist_ok=False)
    #        f = open(os.path.join(idir,"pcbway.png"),"wb")
    #        f.write(idata)
    #        f.close()

    # saving the file as step
    tf = tempfile.NamedTemporaryFile(suffix=".stp")
    tf.close()
    shape.exportStep(tf.name)
    bb = shape.BoundBox

    # prepare and upload data
    data = MultiPartData()
    data.add_field('Length', bb.XLength)
    data.add_field('Width',  bb.YLength)
    data.add_field('Height', bb.ZLength)
    data.add_file('upload[file]', os.path.basename(tf.name), open(tf.name,'r'))
    request = urllib.request.Request(pcb_url)
    request.add_header('User-agent', 'FreeCAD (https://freecad.org)')
    body = data.get_bytes()
    request.add_header('Content-type', data.get_content_type())
    request.add_header('Content-length', len(body))
    rsp = urllib.request.urlopen(request,data=body).read()
    rsp_link = json.loads(rsp.decode('utf8'))['redirect']

    # get the respnse and open a link
    webbrowser.open(rsp_link)



# run when macro is launched
main()

