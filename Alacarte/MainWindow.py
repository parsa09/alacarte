# -*- coding: utf-8 -*-
# vim: set noexpandtab:
#   Alacarte Menu Editor - Simple fd.o Compliant Menu Editor
#   Copyright (C) 2006  Travis Watkins
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

from gi.repository import Gtk, GObject, Gio, GdkPixbuf, Gdk, GMenu
import cgi, os
import gettext
import subprocess
import urllib
import tempfile

from Alacarte import config
gettext.bindtextdomain(config.GETTEXT_PACKAGE, config.localedir)
gettext.textdomain(config.GETTEXT_PACKAGE)

_ = gettext.gettext
from Alacarte.MenuEditor import MenuEditor
from Alacarte import util
import sys

class MainWindow:
    timer = None
    #hack to make editing menu properties work
    allow_update = True
    #drag-and-drop stuff
    dnd_items = [('ALACARTE_ITEM_ROW', Gtk.TargetFlags.SAME_APP, 0), ('text/plain', 0, 1)]
    dnd_menus = [('ALACARTE_MENU_ROW', Gtk.TargetFlags.SAME_APP, 0)]
    dnd_both = [dnd_items[0],] + dnd_menus
    drag_data = None
    edit_pool = []

    def __init__(self, datadir, version, argv):
        self.file_path = datadir
        self.version = version
        self.editor = MenuEditor()
        Gtk.Window.set_default_icon_name('alacarte')
        self.tree = Gtk.Builder()
        self.tree.set_translation_domain(config.GETTEXT_PACKAGE)
        self.tree.add_from_file(os.path.join(self.file_path, 'alacarte.ui'))
        self.tree.connect_signals(self)
        self.setupMenuTree()
        self.setupItemTree()
        self.tree.get_object('edit_delete').set_sensitive(False)
        self.tree.get_object('edit_revert_to_original').set_sensitive(False)
        self.tree.get_object('edit_properties').set_sensitive(False)
        self.tree.get_object('move_up_button').set_sensitive(False)
        self.tree.get_object('move_down_button').set_sensitive(False)
        self.tree.get_object('new_separator_button').set_sensitive(False)
        accelgroup = Gtk.AccelGroup()
        keyval, modifier = Gtk.accelerator_parse('<Ctrl>Z')
        accelgroup.connect(keyval, modifier, Gtk.AccelFlags.VISIBLE, self.on_mainwindow_undo)
        keyval, modifier = Gtk.accelerator_parse('<Ctrl><Shift>Z')
        accelgroup.connect(keyval, modifier, Gtk.AccelFlags.VISIBLE, self.on_mainwindow_redo)
        keyval, modifier = Gtk.accelerator_parse('F1')
        accelgroup.connect(keyval, modifier, Gtk.AccelFlags.VISIBLE, self.on_help_button_clicked)
        self.tree.get_object('mainwindow').add_accel_group(accelgroup)

    def run(self):
        self.loadMenus()
        self.editor.applications.tree.connect("changed", self.menuChanged)
        self.tree.get_object('mainwindow').show_all()
        Gtk.main()

    def menuChanged(self, *a):
        print >> sys.stderr, "changed!\n"
        if self.timer:
            GObject.source_remove(self.timer)
            self.timer = None
        self.timer = GObject.timeout_add(3, self.loadUpdates)

    def loadUpdates(self):
        print >> sys.stderr, "%d\n" % self.editor.applications.tree.disconnect_by_func(self.menuChanged)
        self.editor.reloadMenus()
        self.editor.applications.tree.connect("changed", self.menuChanged)

        if not self.allow_update:
            return False
        menu_tree = self.tree.get_object('menu_tree')
        item_tree = self.tree.get_object('item_tree')
        items, iter = item_tree.get_selection().get_selected()
        update_items = False
        update_type = None
        item_id = None
        if iter:
            update_items = True
            if isinstance(items[iter][3], GMenu.TreeEntry):
                item_id = items[iter][3].get_desktop_file_id()
                update_type = GMenu.TreeItemType.ENTRY
            elif isinstance(items[iter][3], GMenu.TreeDirectory):
                item_id = os.path.split(items[iter][3].get_desktop_file_path())[1]
                update_type = GMenu.TreeItemType.DIRECTORY
            elif isinstance(items[iter][3], GMenu.Tree.Separator):
                item_id = items.get_path(iter)
                update_type = GMenu.TreeItemType.SEPARATOR
        menus, iter = menu_tree.get_selection().get_selected()
        update_menus = False
        menu_id = None
        if iter:
            if menus[iter][2].get_desktop_file_path():
                menu_id = os.path.split(menus[iter][2].get_desktop_file_path())[1]
            else:
                menu_id = menus[iter][2].get_menu_id()
            update_menus = True
        self.loadMenus()
        #find current menu in new tree
        if update_menus:
            menu_tree.get_model().foreach(self.findMenu, menu_id)
            menus, iter = menu_tree.get_selection().get_selected()
            if iter:
                self.on_menu_tree_cursor_changed(menu_tree)
        #find current item in new list
        if update_items:
            i = 0
            for item in item_tree.get_model():
                found = False
                if update_type != GMenu.TreeItemType.SEPARATOR:
                    if isinstance (item[3], GMenu.TreeEntry) and item[3].get_desktop_file_id() == item_id:
                        found = True
                    if isinstance (item[3], GMenu.TreeDirectory) and item[3].get_desktop_file_path() and update_type == GMenu.TreeItemType.DIRECTORY:
                        if os.path.split(item[3].get_desktop_file_path())[1] == item_id:
                            found = True
                if isinstance(item[3], GMenu.TreeSeparator):
                    if not isinstance(item_id, tuple):
                        #we may not skip the increment via "continue"
                        i += 1
                        continue
                    #separators have no id, have to find them manually
                    #probably won't work with two separators together
                    if (item_id[0] - 1,) == (i,):
                        found = True
                    elif (item_id[0] + 1,) == (i,):
                        found = True
                    elif (item_id[0],) == (i,):
                        found = True
                if found:
                    item_tree.get_selection().select_path((i,))
                    self.on_item_tree_cursor_changed(item_tree)
                    break
                i += 1
        return False

    def findMenu(self, menus, path, iter, menu_id):
        if not menus[path][2].get_desktop_file_path():
            if menu_id == menus[path][2].get_menu_id():
                menu_tree = self.tree.get_object('menu_tree')
                menu_tree.expand_to_path(path)
                menu_tree.get_selection().select_path(path)
                return True
            return False
        if os.path.split(menus[path][2].get_desktop_file_path())[1] == menu_id:
            menu_tree = self.tree.get_object('menu_tree')
            menu_tree.expand_to_path(path)
            menu_tree.get_selection().select_path(path)
            return True

    def setupMenuTree(self):
        self.menu_store = Gtk.TreeStore(GdkPixbuf.Pixbuf, str, object)
        menus = self.tree.get_object('menu_tree')
        column = Gtk.TreeViewColumn(_('Name'))
        column.set_spacing(4)
        cell = Gtk.CellRendererPixbuf()
        column.pack_start(cell, False)
        column.add_attribute(cell, 'pixbuf', 0)
        cell = Gtk.CellRendererText()
        column.pack_start(cell, True)
        column.add_attribute(cell, 'markup', 1)
        menus.append_column(column)
        menus.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, self.dnd_menus, Gdk.DragAction.COPY)
        menus.enable_model_drag_dest(self.dnd_both, Gdk.DragAction.PRIVATE)
        menus.get_selection().set_mode(Gtk.SelectionMode.BROWSE)

    def setupItemTree(self):
        items = self.tree.get_object('item_tree')
        column = Gtk.TreeViewColumn(_('Show'))
        cell = Gtk.CellRendererToggle()
        cell.connect('toggled', self.on_item_tree_show_toggled)
        column.pack_start(cell, True)
        column.add_attribute(cell, 'active', 0)
        #hide toggle for separators
        column.set_cell_data_func(cell, self._cell_data_toggle_func)
        items.append_column(column)
        column = Gtk.TreeViewColumn(_('Item'))
        column.set_spacing(4)
        cell = Gtk.CellRendererPixbuf()
        column.pack_start(cell, False)
        column.add_attribute(cell, 'pixbuf', 1)
        cell = Gtk.CellRendererText()
        column.pack_start(cell, True)
        column.add_attribute(cell, 'markup', 2)
        items.append_column(column)
        self.item_store = Gtk.ListStore(bool, GdkPixbuf.Pixbuf, str, object)
        items.set_model(self.item_store)
        items.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, self.dnd_items, Gdk.DragAction.COPY)
        items.enable_model_drag_dest(self.dnd_items, Gdk.DragAction.PRIVATE)

    def _cell_data_toggle_func(self, tree_column, renderer, model, treeiter, data=None):
        if isinstance(model[treeiter][3], GMenu.TreeSeparator):
            renderer.set_property('visible', False)
        else:
            renderer.set_property('visible', True)

    def loadMenus(self):
        self.menu_store.clear()
        for menu in self.editor.getMenus():
            iters = [None]*20
            self.loadMenu(iters, menu)
        menu_tree = self.tree.get_object('menu_tree')
        menu_tree.set_model(self.menu_store)
        for menu in self.menu_store:
            #this might not work for some reason
            try:
                menu_tree.expand_to_path(menu.path)
            except:
                pass
        menu_tree.get_selection().select_path((0,))
        self.on_menu_tree_cursor_changed(menu_tree)

    def loadMenu(self, iters, parent, depth=0):
        if depth == 0:
            icon = util.getIcon(parent)
            iters[depth] = self.menu_store.append(None, (icon, cgi.escape(parent.get_name()), parent))
        depth += 1
        for menu, show in self.editor.getMenus(parent):
            if show:
                name = cgi.escape(menu.get_name())
            else:
                name = '<small><i>' + cgi.escape(menu.get_name()) + '</i></small>'
            icon = util.getIcon(menu)
            iters[depth] = self.menu_store.append(iters[depth-1], (icon, name, menu))
            self.loadMenu(iters, menu, depth)
        depth -= 1

    def loadItems(self, menu, menu_path):
        self.item_store.clear()
        for item, show in self.editor.getItems(menu):
            menu_icon = None
            if isinstance(item, GMenu.TreeSeparator):
                name = '---'
                icon = None
            elif isinstance(item, GMenu.TreeEntry):
                app_info = item.get_app_info()
                if show:
                    name = cgi.escape(app_info.get_display_name())
                else:
                    name = '<small><i>' + cgi.escape(app_info.get_display_name()) + '</i></small>'
                icon = util.getIcon(item)
            else:
                if show:
                    name = cgi.escape(item.get_name())
                else:
                    name = '<small><i>' + cgi.escape(item.get_name()) + '</i></small>'
                icon = util.getIcon(item)
            self.item_store.append((show, icon, name, item))

    #this is a little timeout callback to insert new items after
    #gnome-desktop-item-edit has finished running
    def waitForNewItemProcess(self, process, parent_id, file_path):
        if process.poll() != None:
            if os.path.isfile(file_path):
                self.editor.insertExternalItem(os.path.split(file_path)[1], parent_id)
            return False
        return True

    def waitForNewMenuProcess(self, process, parent_id, file_path):
        if process.poll() != None:
            #hack for broken gnome-desktop-item-edit
            broken_path = os.path.join(os.path.split(file_path)[0], '.directory')
            if os.path.isfile(broken_path):
                os.rename(broken_path, file_path)
            if os.path.isfile(file_path):
                self.editor.insertExternalMenu(os.path.split(file_path)[1], parent_id)
            return False
        return True

    #this callback keeps you from editing the same item twice
    def waitForEditProcess(self, process, file_path):
        if process.poll() != None:
            self.edit_pool.remove(file_path)
            return False
        return True

    def on_new_menu_button_clicked(self, button):
        menu_tree = self.tree.get_object('menu_tree')
        menus, iter = menu_tree.get_selection().get_selected()
        if not iter:
            parent = menus[(0,)][2]
            menu_tree.expand_to_path((0,))
            menu_tree.get_selection().select_path((0,))
        else:
            parent = menus[iter][2]
        file_path = os.path.join(util.getUserDirectoryPath(), util.getUniqueFileId('alacarte-made', '.directory'))
        process = subprocess.Popen(['gnome-desktop-item-edit', file_path], env=os.environ)
        GObject.timeout_add(100, self.waitForNewMenuProcess, process, parent.get_menu_id(), file_path)

    def on_new_item_button_clicked(self, button):
        menu_tree = self.tree.get_object('menu_tree')
        menus, iter = menu_tree.get_selection().get_selected()
        if not iter:
            parent = menus[(0,)][2]
            menu_tree.expand_to_path((0,))
            menu_tree.get_selection().select_path((0,))
        else:
            parent = menus[iter][2]
        file_path = os.path.join(util.getUserItemPath(), util.getUniqueFileId('alacarte-made', '.desktop'))
        process = subprocess.Popen(['gnome-desktop-item-edit', file_path], env=os.environ)
        GObject.timeout_add(100, self.waitForNewItemProcess, process, parent.get_menu_id(), file_path)

    def on_new_separator_button_clicked(self, button):
        item_tree = self.tree.get_object('item_tree')
        items, iter = item_tree.get_selection().get_selected()
        if not iter:
            return
        else:
            after = items[iter][3]
            menu_tree = self.tree.get_object('menu_tree')
            menus, iter = menu_tree.get_selection().get_selected()
            parent = menus[iter][2]
            self.editor.createSeparator(parent, after=after)

    def on_edit_delete_activate(self, menu):
        item_tree = self.tree.get_object('item_tree')
        items, iter = item_tree.get_selection().get_selected()
        if not iter:
            return
        item = items[iter][3]
        if isinstance(item, GMenu.TreeEntry):
            self.editor.deleteItem(item)
        elif isinstance(item, GMenu.TreeDirectory):
            self.editor.deleteMenu(item)
        elif isinstance(item, GMenu.TreeSeparator):
            self.editor.deleteSeparator(item)

    def on_edit_revert_to_original_activate(self, menu):
        item_tree = self.tree.get_object('item_tree')
        items, iter = item_tree.get_selection().get_selected()
        if not iter:
            return
        item = items[iter][3]
        if isinstance(item, GMenu.TreeEntry):
            self.editor.revertItem(item)
        elif isinstance(item, GMenu.TreeDirectory):
            self.editor.revertMenu(item)

    def on_edit_properties_activate(self, menu):
        item_tree = self.tree.get_object('item_tree')
        items, iter = item_tree.get_selection().get_selected()
        if not iter:
            return
        item = items[iter][3]
        if not isinstance(item, GMenu.TreeEntry) and not isinstance(item, GMenu.TreeDirectory):
            return

        if isinstance(item, GMenu.TreeEntry):
            file_path = os.path.join(util.getUserItemPath(), item.get_desktop_file_id())
            file_type = 'Item'
        elif isinstance(item, GMenu.TreeDirectory):
            if item.get_desktop_file_path() == None:
                file_path = util.getUniqueFileId('alacarte-made', '.directory')
                parser = util.DesktopParser(file_path, 'Directory')
                parser.set('Name', item.get_name())
                parser.set('Comment', item.get_comment())
                parser.set('Icon', item.get_icon())
                parser.write(open(file_path))
            else:
                file_path = os.path.join(util.getUserDirectoryPath(), os.path.split(item.get_desktop_file_path())[1])
            file_type = 'Menu'

        if not os.path.isfile(file_path):
            data = open(item.get_desktop_file_path()).read()
            open(file_path, 'w').write(data)
            self.editor._MenuEditor__addUndo([(file_type, os.path.split(file_path)[1]),])
        else:
            self.editor._MenuEditor__addUndo([item,])
        if file_path not in self.edit_pool:
            self.edit_pool.append(file_path)
            process = subprocess.Popen(['gnome-desktop-item-edit', file_path], env=os.environ)
            GObject.timeout_add(100, self.waitForEditProcess, process, file_path)

    def on_menu_tree_cursor_changed(self, treeview):
        menus, iter = treeview.get_selection().get_selected()
        menu_path = menus.get_path(iter)
        item_tree = self.tree.get_object('item_tree')
        item_tree.get_selection().unselect_all()
        self.loadItems(self.menu_store[menu_path][2], menu_path)
        self.tree.get_object('edit_delete').set_sensitive(False)
        self.tree.get_object('edit_revert_to_original').set_sensitive(False)
        self.tree.get_object('edit_properties').set_sensitive(False)
        self.tree.get_object('move_up_button').set_sensitive(False)
        self.tree.get_object('move_down_button').set_sensitive(False)
        self.tree.get_object('new_separator_button').set_sensitive(False)
        self.tree.get_object('properties_button').set_sensitive(False)
        self.tree.get_object('delete_button').set_sensitive(False)

    def on_menu_tree_drag_data_get(self, treeview, context, selection, target_id, etime):
        menus, iter = treeview.get_selection().get_selected()
        self.drag_data = menus[iter][2]

    def on_menu_tree_drag_data_received(self, treeview, context, x, y, selection, info, etime):
        menus = treeview.get_model()
        drop_info = treeview.get_dest_row_at_pos(x, y)
        if drop_info:
            path, position = drop_info
            types_before = (Gtk.TreeViewDropPosition.INTO_OR_BEFORE, Gtk.TreeViewDropPosition.INTO_OR_AFTER)
            types_into = (Gtk.TreeViewDropPosition.INTO_OR_BEFORE, Gtk.TreeViewDropPosition.INTO_OR_AFTER)
            types_after = (Gtk.TreeViewDropPosition.AFTER, Gtk.TreeViewDropPosition.INTO_OR_AFTER)
            if position not in types:
                context.finish(False, False, etime)
                return False
            if selection.target in ('ALACARTE_ITEM_ROW', 'ALACARTE_MENU_ROW'):
                if self.drag_data == None:
                    return False
                item = self.drag_data
                new_parent = menus[path][2]
                treeview.get_selection().select_path(path)
                if isinstance(item, GMenu.TreeEntry):
                    self.editor.copyItem(item, new_parent)
                elif isinstance(item, GMenu.TreeDirectory):
                    if self.editor.moveMenu(item, new_parent) == False:
                        self.loadUpdates()
                elif isinstance(item, GMenu.TreeSeparator):
                    self.editor.moveSeparator(item, new_parent)
                else:
                    context.finish(False, False, etime) 
                context.finish(True, True, etime)
        self.drag_data = None

    def on_item_tree_show_toggled(self, cell, path):
        item = self.item_store[path][3]
        if isinstance(item, GMenu.TreeSeparator):
            return
        if self.item_store[path][0]:
            self.editor.setVisible(item, False)
        else:
            self.editor.setVisible(item, True)
        self.item_store[path][0] = not self.item_store[path][0]

    def on_item_tree_cursor_changed(self, treeview):
        items, iter = treeview.get_selection().get_selected()
        if iter is None:
            return
        item = items[iter][3]
        self.tree.get_object('edit_delete').set_sensitive(True)
        self.tree.get_object('new_separator_button').set_sensitive(True)
        self.tree.get_object('delete_button').set_sensitive(True)
        if self.editor.canRevert(item):
            self.tree.get_object('edit_revert_to_original').set_sensitive(True)
        else:
            self.tree.get_object('edit_revert_to_original').set_sensitive(False)
        if not isinstance(item, GMenu.TreeSeparator):
            self.tree.get_object('edit_properties').set_sensitive(True)
            self.tree.get_object('properties_button').set_sensitive(True)
        else:
            self.tree.get_object('edit_properties').set_sensitive(False)
            self.tree.get_object('properties_button').set_sensitive(False)

        # If first item...
        if items.get_path(iter).get_indices()[0] == 0:
            self.tree.get_object('move_up_button').set_sensitive(False)
        else:
            self.tree.get_object('move_up_button').set_sensitive(True)

        # If last item...
        if items.get_path(iter).get_indices()[0] == (len(items)-1):
            self.tree.get_object('move_down_button').set_sensitive(False)
        else:
            self.tree.get_object('move_down_button').set_sensitive(True)

    def on_item_tree_row_activated(self, treeview, path, column):
        self.on_edit_properties_activate(None)

    def on_item_tree_popup_menu(self, item_tree, event=None):
        model, iter = item_tree.get_selection().get_selected()
        if event:
            #don't show if it's not the right mouse button
            if event.button != 3:
                return
            button = event.button
            event_time = event.time
            info = item_tree.get_path_at_pos(int(event.x), int(event.y))
            if info != None:
                path, col, cellx, celly = info
                item_tree.grab_focus()
                item_tree.set_cursor(path, col, 0)
        else:
            path = model.get_path(iter)
            button = 0
            event_time = 0
            item_tree.grab_focus()
            item_tree.set_cursor(path, item_tree.get_columns()[0], 0)
        popup = self.tree.get_object('edit_menu')
        popup.popup(None, None, None, button, event_time)
        #without this shift-f10 won't work
        return True

    def on_item_tree_drag_data_get(self, treeview, context, selection, target_id, etime):
        items, iter = treeview.get_selection().get_selected()
        self.drag_data = items[iter][3]

    def on_item_tree_drag_data_received(self, treeview, context, x, y, selection, info, etime):
        items = treeview.get_model()
        types = (Gtk.TreeViewDropPosition.BEFORE, Gtk.TreeViewDropPosition.INTO_OR_BEFORE)
        if selection.target == 'ALACARTE_ITEM_ROW':
            drop_info = treeview.get_dest_row_at_pos(x, y)
            before = None
            after = None
            if self.drag_data == None:
                return False
            item = self.drag_data
            # by default we assume, that the items stays in the same menu
            destination = item.get_parent()
            if drop_info:
                path, position = drop_info
                target = items[path][3]
                # move the item to the directory, if the item was dropped into it
                if isinstance(target, GMenu.TreeDirectory) and (position in types_into):
                    # append the selected item to the choosen menu
                    destination = target
                elif position in types_before:
                    before = target
                elif position in types_after:
                    after = target
                else:
                    # this does not happen
                    pass
            else:
                path = (len(items) - 1,)
                after = items[path][3]
            if isinstance(item, GMenu.TreeEntry):
                self.editor.moveItem(item, destination, before, after)
            elif isinstance(item, GMenu.TreeDirectory):
                if self.editor.moveMenu(item, destination, before, after) == False:
                    self.loadUpdates()
            elif isinstance(item, GMenu.TreeSeparator):
                self.editor.moveSeparator(item, destination, before, after)
            context.finish(True, True, etime)
        elif selection.target == 'text/plain':
            if selection.data == None:
                return False
            menus, iter = self.tree.get_object('menu_tree').get_selection().get_selected()
            parent = menus[iter][2]
            drop_info = treeview.get_dest_row_at_pos(x, y)
            before = None
            after = None
            if drop_info:
                path, position = drop_info
                if position in types:
                    before = items[path][3]
                else:
                    after = items[path][3]
            else:
                path = (len(items) - 1,)
                after = items[path][3]
            file_path = urllib.unquote(selection.data).strip()
            if not file_path.startswith('file:'):
                return
            myfile = Gio.File(uri=file_path)
            file_info = myfile.query_info(Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE)
            content_type = file_info.get_content_type()
            if content_type == 'application/x-desktop':
                input_stream = myfile.read()
                (fd, tmppath) = tempfile.mkstemp(prefix='alacarte-dnd', suffix='.desktop')
                os.close(fd)
                f = os.open(tmppath, 'w')
                f.write(input_stream.read())
                f.close()
                parser = util.DesktopParser(tmppath)
                self.editor.createItem(parent, parser.get('Icon'), parser.get('Name', self.editor.locale), parser.get('Comment', self.editor.locale), parser.get('Exec'), parser.get('Terminal'), before, after)
            elif content_type in ('application/x-shellscript', 'application/x-executable'):
                self.editor.createItem(parent, None, os.path.split(file_path)[1].strip(), None, file_path.replace('file://', '').strip(), False, before, after)
        self.drag_data = None

    def on_item_tree_key_press_event(self, item_tree, event):
        if event.keyval == Gdk.KEY_Delete:
            self.on_edit_delete_activate(item_tree)

    def on_move_up_button_clicked(self, button):
        item_tree = self.tree.get_object('item_tree')
        items, iter = item_tree.get_selection().get_selected()
        if not iter:
            return
        path = items.get_path(iter)
        #at top, can't move up
        if path.get_indices()[0] == 0:
            return
        item = items[path][3]
        before = items[(path.get_indices()[0] - 1,)][3]
        if isinstance(item, GMenu.TreeEntry):
            self.editor.moveItem(item, item.get_parent(), before=before)
        elif isinstance(item, GMenu.TreeDirectory):
            self.editor.moveMenu(item, item.get_parent(), before=before)
        elif isinstance(item, GMenu.TreeSeparator):
            self.editor.moveSeparator(item, item.get_parent(), before=before)

    def on_move_down_button_clicked(self, button):
        item_tree = self.tree.get_object('item_tree')
        items, iter = item_tree.get_selection().get_selected()
        if not iter:
            return
        path = items.get_path(iter)
        #at bottom, can't move down
        if path.get_indices()[0] == (len(items) - 1):
            return
        item = items[path][3]
        after = items[path][3]
        if isinstance(item, GMenu.TreeEntry):
            self.editor.moveItem(item, item.get_parent(), after=after)
        elif isinstance(item, GMenu.TreeDirectory):
            self.editor.moveMenu(item, item.get_parent(), after=after)
        elif isinstance(item, GMenu.TreeSeparator):
            self.editor.moveSeparator(item, item.get_parent(), after=after)

    def on_mainwindow_undo(self, accelgroup, window, keyval, modifier):
        self.editor.undo()

    def on_mainwindow_redo(self, accelgroup, window, keyval, modifier):
        self.editor.redo()

    def on_help_button_clicked(self, *args):
        Gtk.show_uri(Gdk.Screen.get_default(), "ghelp:user-guide#menu-editor", Gtk.get_current_event_time())

    def on_revert_button_clicked(self, button):
        dialog = self.tree.get_object('revertdialog')
        dialog.set_transient_for(self.tree.get_object('mainwindow'))
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.YES:
            self.editor.revert()
        dialog.hide()

    def on_close_button_clicked(self, button):
        try:
            self.tree.get_object('mainwindow').hide()
        except:
            pass
        GObject.timeout_add(10, self.quit)

    def on_properties_button_clicked(self, button):
        self.on_edit_properties_activate(None)
    def on_delete_button_clicked(self, button):
        self.on_edit_delete_activate(None)

    def on_style_set(self, *args):
        self.loadUpdates()

    def quit(self):
        self.editor.quit()
        Gtk.main_quit()
