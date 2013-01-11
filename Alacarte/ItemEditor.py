# -*- coding: utf-8 -*-
#   Alacarte Menu Editor - Simple fd.o Compliant Menu Editor
#   Copyright (C) 2013  Red Hat, Inc.
#
#   This library is free software; you can redistribute it and/or
#   modify it under the terms of the GNU Library General Public
#   License as published by the Free Software Foundation; either
#   version 2 of the License, or (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#   Library General Public License for more details.
#
#   You should have received a copy of the GNU Library General Public
#   License along with this library; if not, write to the Free Software
#   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import gettext
import os
from gi.repository import GLib, Gtk
from Alacarte import config, util

from gi._glib import GError

_ = gettext.gettext

EXTENSIONS = (".png", ".xpm", ".svg")

def try_icon_name(filename):
    # Detect if the user picked an icon, and make
    # it into an icon name.
    if not filename.endswith(EXTENSIONS):
        return filename

    filename = filename[:-4]

    theme = Gtk.IconTheme.get_default()
    resolved_path = None
    for path in theme.get_search_path():
        if filename.startswith(path):
            resolved_path = filename[len(path):].lstrip(os.sep)
            break

    if resolved_path is None:
        return filename

    parts = resolved_path.split(os.sep)
    # icon-theme/size/category/icon
    if len(parts) != 4:
        return filename

    return parts[3]

def get_icon_string(image):
    filename = image.props.file
    if filename is not None:
        return try_icon_name(filename)

    return image.props.icon_name

def strip_extensions(icon):
    if icon.endswith(EXTENSIONS):
        return icon[:-4]
    else:
        return icon

def set_icon_string(image, icon):
    if GLib.path_is_absolute(icon):
        image.props.file = icon
    else:
        image.props.icon_name = strip_extensions(icon)

DESKTOP_GROUP = GLib.KEY_FILE_DESKTOP_GROUP

class LauncherEditor(object):
    def __init__(self, item_path):
        self.builder = Gtk.Builder()
        self.builder.add_from_file('data/launcher-editor.ui')

        self.dialog = self.builder.get_object('launcher-editor')
        self.dialog.connect('response', self.on_response)

        self.builder.get_object('icon-button').connect('clicked', self.pick_icon)
        self.builder.get_object('exec-browse').connect('clicked', self.pick_exec)

        self.item_path = item_path
        self.load()

    def load(self):
        self.keyfile = GLib.KeyFile()
        try:
            self.keyfile.load_from_file(self.item_path, util.KEY_FILE_FLAGS)
        except IOError:
            return

        def set_text(ctl, name):
            try:
                val = self.keyfile.get_string(DESKTOP_GROUP, name)
            except GError:
                pass
            else:
                self.builder.get_object(ctl).set_text(val)

        def set_check(ctl, name):
            try:
                val = self.keyfile.get_boolean(DESKTOP_GROUP, name)
            except GError:
                pass
            else:
                self.builder.get_object(ctl).set_active(val)

        def set_icon(ctl, name):
            try:
                val = self.keyfile.get_string(DESKTOP_GROUP, name)
            except GError:
                pass
            else:
                set_icon_string(self.builder.get_object(ctl), val)

        set_text('name-entry', "Name")
        set_text('exec-entry', "Exec")
        set_text('comment-entry', "Comment")
        set_check('terminal-check', "Terminal")
        set_icon('icon-image', "Icon")

    def run(self):
        self.dialog.present()

    def save(self):
        params = dict(Name=self.builder.get_object('name-entry').get_text(),
                      Exec=self.builder.get_object('exec-entry').get_text(),
                      Comment=self.builder.get_object('comment-entry').get_text(),
                      Terminal=self.builder.get_object('terminal-check').get_active(),
                      Icon=get_icon_string(self.builder.get_object('icon-image')))
        util.fillKeyFile(self.keyfile, params)

        contents, length = self.keyfile.to_data()
        with open(self.item_path, 'w') as f:
            f.write(contents)

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            self.save()
        self.dialog.destroy()

    def pick_icon(self, button):
        chooser = Gtk.FileChooserDialog(title=_("Choose an icon"),
                                        parent=self.dialog,
                                        buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT,
                                        Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))
        response = chooser.run()
        if response == Gtk.ResponseType.ACCEPT:
            self.builder.get_object('icon-image').props.file = chooser.get_filename()
        chooser.destroy()

    def pick_exec(self, button):
        chooser = Gtk.FileChooserDialog(title=_("Choose a command"),
                                        parent=self.dialog,
                                        buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT,
                                        Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))
        response = chooser.run()
        if response == Gtk.ResponseType.ACCEPT:
            self.builder.get_object('exec-entry').set_text(chooser.get_filename())
        chooser.destroy()

def test():
    import sys

    Gtk.Window.set_default_icon_name('alacarte')
    editor = LauncherEditor(sys.argv[1])
    editor.dialog.connect('destroy', Gtk.main_quit)
    editor.run()
    Gtk.main()

if __name__ == "__main__":
    test()
