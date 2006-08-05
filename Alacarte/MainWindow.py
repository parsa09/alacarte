# -*- coding: utf-8 -*-
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

import gtk, gtk.glade, gmenu, gobject, gnomevfs, gnome.ui
import cgi, os
import gettext
gettext.bindtextdomain('alacarte')
gettext.textdomain('alacarte')
gtk.glade.bindtextdomain('alacarte')
gtk.glade.textdomain('alacarte')
_ = gettext.gettext
from Alacarte.MenuEditor import MenuEditor
from Alacarte.DialogHandler import DialogHandler
from Alacarte import util
import time

class MainWindow:
	timer = None
	#hack to make editing menu properties work
	allow_update = True
	#drag-and-drop stuff
	dnd_items = [('ALACARTE_ITEM_ROW', gtk.TARGET_SAME_APP, 0), ('text/plain', 0, 1)]
	dnd_menus = [('ALACARTE_MENU_ROW', gtk.TARGET_SAME_APP, 0)]
	dnd_both = [dnd_items[0],] + dnd_menus
	drag_data = None

	def __init__(self, datadir, version, argv):
		self.file_path = datadir
		self.version = version
		self.editor = MenuEditor()
		gtk.window_set_default_icon_name('alacarte')
		self.tree = gtk.glade.XML(os.path.join(self.file_path, 'alacarte.glade'))
		signals = {}
		for attr in dir(self):
			signals[attr] = getattr(self, attr)
		self.tree.signal_autoconnect(signals)
		self.setupMenuTree()
		self.setupItemTree()
		self.dialogs = DialogHandler(self.tree.get_widget('mainwindow'), self.editor, self.file_path)
		self.tree.get_widget('edit_delete').set_sensitive(False)
		self.tree.get_widget('edit_revert_to_original').set_sensitive(False)
		self.tree.get_widget('edit_properties').set_sensitive(False)
		self.tree.get_widget('move_up_button').set_sensitive(False)
		self.tree.get_widget('move_down_button').set_sensitive(False)
		accelgroup = gtk.AccelGroup()
		keyval, modifier = gtk.accelerator_parse('<Ctrl>Z')
		accelgroup.connect_group(keyval, modifier, gtk.ACCEL_VISIBLE, self.on_mainwindow_undo)
		keyval, modifier = gtk.accelerator_parse('<Ctrl><Shift>Z')
		accelgroup.connect_group(keyval, modifier, gtk.ACCEL_VISIBLE, self.on_mainwindow_redo)
		self.tree.get_widget('mainwindow').add_accel_group(accelgroup)
		gnome.ui.authentication_manager_init()

	def run(self):
		self.loadMenus()
		self.editor.applications.tree.add_monitor(self.menuChanged, None)
		self.editor.settings.tree.add_monitor(self.menuChanged, None)
		self.tree.get_widget('mainwindow').show_all()
		gtk.main()

	def menuChanged(self, *a):
		if self.timer:
			gobject.source_remove(self.timer)
			self.timer = None
		self.timer = gobject.timeout_add(3, self.loadUpdates)

	def loadUpdates(self):
		if not self.allow_update:
			return False
		menu_tree = self.tree.get_widget('menu_tree')
		item_tree = self.tree.get_widget('item_tree')
		items, iter = item_tree.get_selection().get_selected()
		update_items = False
		item_id, separator_path = None, None
		if iter:
			update_items = True
			if items[iter][3].get_type() == gmenu.TYPE_DIRECTORY:
				item_id = os.path.split(items[iter][3].get_desktop_file_path())[1]
				update_items = True
			elif items[iter][3].get_type() == gmenu.TYPE_ENTRY:
				item_id = items[iter][3].get_desktop_file_id()
				update_items = True
			elif items[iter][3].get_type() == gmenu.TYPE_SEPARATOR:
				item_id = items.get_path(iter)
				update_items = True
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
				if item[3].get_type() == gmenu.TYPE_ENTRY and item[3].get_desktop_file_id() == item_id:
					found = True
				if item[3].get_type() == gmenu.TYPE_DIRECTORY and item[3].get_desktop_file_path():
					if os.path.split(item[3].get_desktop_file_path())[1] == item_id:
						found = True
				if item[3].get_type() == gmenu.TYPE_SEPARATOR:
					if not isinstance(item_id, tuple):
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
				menu_tree = self.tree.get_widget('menu_tree')
				menu_tree.expand_to_path(path)
				menu_tree.get_selection().select_path(path)
				return True
			return False
		if os.path.split(menus[path][2].get_desktop_file_path())[1] == menu_id:
			menu_tree = self.tree.get_widget('menu_tree')
			menu_tree.expand_to_path(path)
			menu_tree.get_selection().select_path(path)
			return True

	def setupMenuTree(self):
		self.menu_store = gtk.TreeStore(gtk.gdk.Pixbuf, str, object)
		menus = self.tree.get_widget('menu_tree')
		column = gtk.TreeViewColumn(_('Name'))
		column.set_spacing(4)
		cell = gtk.CellRendererPixbuf()
		column.pack_start(cell, False)
		column.set_attributes(cell, pixbuf=0)
		cell = gtk.CellRendererText()
		cell.set_fixed_size(-1, 25)
		column.pack_start(cell, True)
		column.set_attributes(cell, markup=1)
		column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		menus.append_column(column)
		menus.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, self.dnd_menus, gtk.gdk.ACTION_COPY)
		menus.enable_model_drag_dest(self.dnd_both, gtk.gdk.ACTION_PRIVATE)

	def setupItemTree(self):
		items = self.tree.get_widget('item_tree')
		column = gtk.TreeViewColumn(_('Show'))
		cell = gtk.CellRendererToggle()
		cell.connect('toggled', self.on_item_tree_show_toggled)
		column.pack_start(cell, True)
		column.set_attributes(cell, active=0)
		#hide toggle for separators
		column.set_cell_data_func(cell, self._cell_data_toggle_func)
		items.append_column(column)
		column = gtk.TreeViewColumn(_('Item'))
		column.set_spacing(4)
		cell = gtk.CellRendererPixbuf()
		column.pack_start(cell, False)
		column.set_attributes(cell, pixbuf=1)
		cell = gtk.CellRendererText()
		cell.set_fixed_size(-1, 25)
		column.pack_start(cell, True)
		column.set_attributes(cell, markup=2)
		items.append_column(column)
		self.item_store = gtk.ListStore(bool, gtk.gdk.Pixbuf, str, object)
		items.set_model(self.item_store)
		items.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, self.dnd_items, gtk.gdk.ACTION_COPY)
		items.enable_model_drag_dest(self.dnd_items, gtk.gdk.ACTION_PRIVATE)

	def _cell_data_toggle_func(self, tree_column, renderer, model, treeiter):
		if model[treeiter][3].get_type() == gmenu.TYPE_SEPARATOR:
			renderer.set_property('visible', False)
		else:
			renderer.set_property('visible', True)

	def loadMenus(self):
		self.menu_store.clear()
		for menu in self.editor.getMenus():
			iters = [None]*20
			self.loadMenu(iters, menu)
		menu_tree = self.tree.get_widget('menu_tree')
		menu_tree.set_model(self.menu_store)
		for menu in self.menu_store:
			menu_tree.expand_to_path(menu.path)
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
			if item.get_type() == gmenu.TYPE_SEPARATOR:
				name = '---'
				icon = None
			else:
				if show:
					name = cgi.escape(item.get_name())
				else:
					name = '<small><i>' + cgi.escape(item.get_name()) + '</i></small>'
				icon = util.getIcon(item)
			self.item_store.append((show, icon, name, item))

	def on_new_menu_button_clicked(self, button):
		menu_tree = self.tree.get_widget('menu_tree')
		menus, iter = menu_tree.get_selection().get_selected()
		if not iter:
			parent = menus[(0,)][2]
			menu_tree.expand_to_path((0,))
			menu_tree.get_selection().select_path((0,))
		else:
			parent = menus[iter][2]
		values = self.dialogs.newMenuDialog()
		if values:
			self.editor.createMenu(parent, values[0], values[1], values[2])
		#FIXME: make gnome-menus update monitors when menus are added
		gobject.timeout_add(3, self.loadUpdates)

	def on_new_item_button_clicked(self, button):
		menu_tree = self.tree.get_widget('menu_tree')
		menus, iter = menu_tree.get_selection().get_selected()
		if not iter:
			parent = menus[(0,)][2]
			menu_tree.expand_to_path((0,))
			menu_tree.get_selection().select_path((0,))
		else:
			parent = menus[iter][2]
		values = self.dialogs.newItemDialog()
		if values:
			self.editor.createItem(parent, values[0], values[1], values[2], values[3], values[4])

	def on_new_separator_button_clicked(self, button):
		item_tree = self.tree.get_widget('item_tree')
		items, iter = item_tree.get_selection().get_selected()
		if not iter:
			return
		else:
			after = items[iter][3]
			menu_tree = self.tree.get_widget('menu_tree')
			menus, iter = menu_tree.get_selection().get_selected()
			parent = menus[iter][2]
			self.editor.createSeparator(parent, after=after)

	def on_edit_delete_activate(self, menu):
		item_tree = self.tree.get_widget('item_tree')
		items, iter = item_tree.get_selection().get_selected()
		if not iter:
			return
		item = items[iter][3]
		if item.get_type() == gmenu.TYPE_ENTRY:
			self.editor.deleteItem(item)
		elif item.get_type() == gmenu.TYPE_DIRECTORY:
			self.editor.deleteMenu(item)
		elif item.get_type() == gmenu.TYPE_SEPARATOR:
			self.editor.deleteSeparator(item)

	def on_edit_revert_to_original_activate(self, menu):
		item_tree = self.tree.get_widget('item_tree')
		items, iter = item_tree.get_selection().get_selected()
		if not iter:
			return
		item = items[iter][3]
		if item.get_type() == gmenu.TYPE_ENTRY:
			self.editor.revertItem(item)
		elif item.get_type() == gmenu.TYPE_DIRECTORY:
			self.editor.revertMenu(item)

	def on_edit_properties_activate(self, menu):
		item_tree = self.tree.get_widget('item_tree')
		items, iter = item_tree.get_selection().get_selected()
		if not iter:
			return
		item = items[iter][3]
		self.allow_update = False
		if item.get_type() == gmenu.TYPE_ENTRY:
			self.dialogs.editItemDialog(items[iter])
		elif item.get_type() == gmenu.TYPE_DIRECTORY:
			self.dialogs.editMenuDialog(items[iter])
		self.allow_update = True
		self.loadUpdates()

	def on_menu_tree_cursor_changed(self, treeview):
		menus, iter = treeview.get_selection().get_selected()
		menu_path = menus.get_path(iter)
		item_tree = self.tree.get_widget('item_tree')
		item_tree.get_selection().unselect_all()
		self.loadItems(self.menu_store[menu_path][2], menu_path)
		self.tree.get_widget('edit_delete').set_sensitive(False)
		self.tree.get_widget('edit_revert_to_original').set_sensitive(False)
		self.tree.get_widget('edit_properties').set_sensitive(False)
		self.tree.get_widget('move_up_button').set_sensitive(False)
		self.tree.get_widget('move_down_button').set_sensitive(False)

	def on_menu_tree_drag_data_get(self, treeview, context, selection, target_id, etime):
		menus, iter = treeview.get_selection().get_selected()
		self.drag_data = menus[iter][2]

	def on_menu_tree_drag_data_received(self, treeview, context, x, y, selection, info, etime):
		menus = treeview.get_model()
		drop_info = treeview.get_dest_row_at_pos(x, y)
		if drop_info:
			path, position = drop_info
			types = (gtk.TREE_VIEW_DROP_INTO_OR_BEFORE, gtk.TREE_VIEW_DROP_INTO_OR_AFTER)
			if position not in types:
				context.finish(False, False, etime)
				return False
			if selection.target in ('ALACARTE_ITEM_ROW', 'ALACARTE_MENU_ROW'):
				item = self.drag_data
				new_parent = menus[path][2]
				treeview.get_selection().select_path(path)
				if item.get_type() == gmenu.TYPE_ENTRY:
					self.editor.copyItem(item, new_parent)
				elif item.get_type() == gmenu.TYPE_DIRECTORY:
					if self.editor.moveMenu(item, new_parent) == False:
						self.loadUpdates()
				else:
					context.finish(False, False, etime) 
				context.finish(True, True, etime)

	def on_item_tree_show_toggled(self, cell, path):
		item = self.item_store[path][3]
		if item.get_type() == gmenu.TYPE_SEPARATOR:
			return
		if self.item_store[path][0]:
			self.editor.setVisible(item, False)
		else:
			self.editor.setVisible(item, True)

	def on_item_tree_cursor_changed(self, treeview):
		items, iter = treeview.get_selection().get_selected()
		item = items[iter][3]
		self.tree.get_widget('edit_delete').set_sensitive(True)
		if self.editor.canRevert(item):
			self.tree.get_widget('edit_revert_to_original').set_sensitive(True)
		else:
			self.tree.get_widget('edit_revert_to_original').set_sensitive(False)
		if not item.get_type() == gmenu.TYPE_SEPARATOR:
			self.tree.get_widget('edit_properties').set_sensitive(True)
		else:
			self.tree.get_widget('edit_properties').set_sensitive(False)
		self.tree.get_widget('move_up_button').set_sensitive(True)
		self.tree.get_widget('move_down_button').set_sensitive(True)

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
		popup = self.tree.get_widget('edit_menu')
		popup.popup(None, None, None, button, event_time)
		#without this shift-f10 won't work
		return True

	def on_item_tree_drag_data_get(self, treeview, context, selection, target_id, etime):
		items, iter = treeview.get_selection().get_selected()
		self.drag_data = items[iter][3]

	def on_item_tree_drag_data_received(self, treeview, context, x, y, selection, info, etime):
		items = treeview.get_model()
		types = (gtk.TREE_VIEW_DROP_BEFORE,	gtk.TREE_VIEW_DROP_INTO_OR_BEFORE)
		if selection.target == 'ALACARTE_ITEM_ROW':
			drop_info = treeview.get_dest_row_at_pos(x, y)
			before = None
			after = None
			item = self.drag_data
			if drop_info:
				path, position = drop_info
				if position in types:
					before = items[path][3]
				else:
					after = items[path][3]
			else:
				path = (len(items) - 1,)
				after = items[path][3]
			if item.get_type() == gmenu.TYPE_ENTRY:
				self.editor.moveItem(item, item.get_parent(), before, after)
			elif item.get_type() == gmenu.TYPE_DIRECTORY:
				if self.editor.moveMenu(item, item.get_parent(), before, after) == False:
					self.loadUpdates()
			elif item.get_type() == gmenu.TYPE_SEPARATOR:
				self.editor.moveSeparator(item, item.get_parent(), before, after)
			context.finish(True, True, etime)
		elif selection.target == 'text/plain':
			menus, iter = self.tree.get_widget('menu_tree').get_selection().get_selected()
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
			file_path = gnomevfs.unescape_string(selection.data, '').strip()
			if not file_path.startswith('file:'):
				return
			file_info = gnomevfs.get_file_info(
				file_path, gnomevfs.FILE_INFO_GET_MIME_TYPE|
				gnomevfs.FILE_INFO_FORCE_SLOW_MIME_TYPE|
				gnomevfs.FILE_INFO_FOLLOW_LINKS|gnomevfs.FILE_INFO_DEFAULT
				)
			if file_info.mime_type == 'application/x-desktop':
				handle = gnomevfs.open(file_path)
				data = handle.read(file_info.size)
				open('/tmp/alacarte-dnd.desktop', 'w').write(data)
				parser = util.DesktopParser('/tmp/alacarte-dnd.desktop')
				self.editor.createItem(parent, parser.get('Icon'), parser.get('Name', self.editor.locale), parser.get('Comment', self.editor.locale), parser.get('Exec'), parser.get('Terminal'), before, after)
			elif file_info.mime_type in ('application/x-shellscript', 'application/x-executable'):
				self.editor.createItem(parent, None, os.path.split(file_path)[1].strip(), None, file_path.replace('file://', '').strip(), False, before, after)

	def on_item_tree_key_press_event(self, item_tree, event):
		if event.keyval == gtk.keysyms.Delete:
			self.on_edit_delete_activate(item_tree)

	def on_move_up_button_clicked(self, button):
		item_tree = self.tree.get_widget('item_tree')
		items, iter = item_tree.get_selection().get_selected()
		if not iter:
			return
		path = items.get_path(iter)
		#at top, can't move up
		if path[0] == 0:
			return
		item = items[path][3]
		before = items[(path[0] - 1,)][3]
		if item.get_type() == gmenu.TYPE_ENTRY:
			self.editor.moveItem(item, item.get_parent(), before=before)
		elif item.get_type() == gmenu.TYPE_DIRECTORY:
			self.editor.moveMenu(item, item.get_parent(), before=before)
		elif item.get_type() == gmenu.TYPE_SEPARATOR:
			self.editor.moveSeparator(item, item.get_parent(), before=before)

	def on_move_down_button_clicked(self, button):
		item_tree = self.tree.get_widget('item_tree')
		items, iter = item_tree.get_selection().get_selected()
		if not iter:
			return
		path = items.get_path(iter)
		#at bottom, can't move down
		if path[0] == (len(items) - 1):
			return
		item = items[path][3]
		after = items[path][3]
		if item.get_type() == gmenu.TYPE_ENTRY:
			self.editor.moveItem(item, item.get_parent(), after=after)
		elif item.get_type() == gmenu.TYPE_DIRECTORY:
			self.editor.moveMenu(item, item.get_parent(), after=after)
		elif item.get_type() == gmenu.TYPE_SEPARATOR:
			self.editor.moveSeparator(item, item.get_parent(), after=after)

	def on_mainwindow_undo(self, accelgroup, window, keyval, modifier):
		self.editor.undo()

	def on_mainwindow_redo(self, accelgroup, window, keyval, modifier):
		self.editor.redo()

	def on_revert_button_clicked(self, button):
		dialog = self.tree.get_widget('revertdialog')
		dialog.set_transient_for(self.tree.get_widget('mainwindow'))
		dialog.show_all()
		if dialog.run() == gtk.RESPONSE_YES:
			self.editor.revert()
		dialog.hide()

	def on_close_button_clicked(self, button):
		try:
			self.tree.get_widget('mainwindow').hide()
		except:
			pass
		gobject.timeout_add(10, self.quit)

	def quit(self):
		self.editor.quit()
		gtk.main_quit()		
