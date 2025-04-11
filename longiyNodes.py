# SPDX-License-Identifier: GPL-2.0-or-later

bl_info = {
    "name": "longiyNodes",
    "description": "Useful and time-saving tools for node group workflow",
    "author": "Campbell Barton, Stephan Kellermayr, longiy",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "Node Editors > Add > longiy",
    "category": "Node",
}

import os
import bpy
from bpy.types import (
    Operator,
    Menu,
    AddonPreferences,
)

from bpy.props import (
    StringProperty,
)


# -----------------------------------------------------------------------------
# Node Adding Operator


def node_center(context):
    from mathutils import Vector
    loc = Vector((0.0, 0.0))
    node_selected = context.selected_nodes
    if node_selected:
        for node in node_selected:
            loc += node.location
        loc /= len(node_selected)
    return loc


def node_template_add(context, filepath, node_group, ungroup, report):
    """ Main function
    """

    space = context.space_data
    node_tree = space.edit_tree  # Updated for Blender 4.4
    node_active = context.active_node
    node_selected = context.selected_nodes

    if node_tree is None:
        report({'ERROR'}, "No node tree available")
        return

    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
        assert(node_group in data_from.node_groups)
        data_to.node_groups = [node_group]
    node_group = data_to.node_groups[0]

    # add node!
    center = node_center(context)

    for node in node_tree.nodes:
        node.select = False

    # Updated node type dictionary for Blender 4.4
    node_type_string = {
        "ShaderNodeTree": "ShaderNodeGroup",
        "CompositorNodeTree": "CompositorNodeGroup",
        "TextureNodeTree": "TextureNodeGroup",
        "GeometryNodeTree": "GeometryNodeGroup",
    }[type(node_tree).__name__]

    node = node_tree.nodes.new(type=node_type_string)
    node.node_tree = node_group

    is_fail = (node.node_tree is None)
    if is_fail:
        report({'WARNING'}, "Incompatible node type")

    node.select = True
    node_tree.nodes.active = node
    node.location = center

    if is_fail:
        node_tree.nodes.remove(node)
    else:
        if ungroup:
            bpy.ops.node.group_ungroup()


# -----------------------------------------------------------------------------
# Node Template Prefs

def node_search_path(context, ui_type):
    preferences = context.preferences
    addon_prefs = preferences.addons[__name__].preferences
    node_paths = {
        "GeometryNodeTree": addon_prefs.search_path_geometry,
        "ShaderNodeTree": addon_prefs.search_path_shader,
        "CompositorNodeTree": addon_prefs.search_path_compositing,
        "TextureNodeTree": addon_prefs.search_path_texture,
    }
    return node_paths.get(ui_type)


class NodeTemplatePrefs(AddonPreferences):
    bl_idname = __name__

    search_path_geometry: StringProperty(
        name="Geometry nodes path",
        subtype='DIR_PATH',
    )
    search_path_shader: StringProperty(
        name="Shader nodes path",
        subtype='DIR_PATH',
    )
    search_path_compositing: StringProperty(
        name="Compositing nodes path",
        subtype='DIR_PATH',
    )
    search_path_texture: StringProperty(
        name="Texture nodes path",
        subtype='DIR_PATH',
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "search_path_geometry")
        layout.prop(self, "search_path_shader")
        layout.prop(self, "search_path_compositing")
        layout.prop(self, "search_path_texture")



class NODE_OT_template_add(Operator):
    """Add a node template"""
    bl_idname = "node.template_add"
    bl_label = "Add node group template"
    bl_description = "Add node group template"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(
        subtype='FILE_PATH',
    )
    group_name: StringProperty()

    @classmethod
    def poll(cls, context):
        return hasattr(context.space_data, 'edit_tree') and context.space_data.edit_tree is not None

    def execute(self, context):
        node_template_add(context, self.filepath, self.group_name, True, self.report)

        return {'FINISHED'}

    def invoke(self, context, event):
        node_template_add(context, self.filepath, self.group_name, event.shift, self.report)

        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Node menu list

def get_ui_type_from_context(context):
    # Helper function to get the current node editor type
    if not context.area:
        return None
    
    if context.area.ui_type in {"GeometryNodeTree", "ShaderNodeTree", 
                               "CompositorNodeTree", "TextureNodeTree",
                               }:
        return context.area.ui_type
    
    # Handle case where node editor is open but we're looking at the wrong area
    for area in context.screen.areas:
        if area.type == 'NODE_EDITOR':
            return area.ui_type
    
    return None


def node_template_cache(context, *, reload=False):
    ui_type = get_ui_type_from_context(context)
    if not ui_type:
        return []
    
    dirpath = node_search_path(context, ui_type)
    if not dirpath or not os.path.exists(dirpath):
        return []

    # Cache variables for each node type
    if ui_type == "GeometryNodeTree":
        if node_template_cache._node_cache_geometry_path != dirpath:
            reload = True
        node_cache = node_template_cache._node_cache_geometry
    elif ui_type == "ShaderNodeTree":
        if node_template_cache._node_cache_shader_path != dirpath:
            reload = True
        node_cache = node_template_cache._node_cache_shader
    elif ui_type == "CompositorNodeTree":
        if node_template_cache._node_cache_compositing_path != dirpath:
            reload = True
        node_cache = node_template_cache._node_cache_compositing
    elif ui_type == "TextureNodeTree":
        if node_template_cache._node_cache_texture_path != dirpath:
            reload = True
        node_cache = node_template_cache._node_cache_texture

    else:
        return []

    if reload:
        node_cache = []
    if node_cache:
        return node_cache

    if not os.path.exists(dirpath):
        return []

    for fn in os.listdir(dirpath):
        if fn.endswith(".blend"):
            filepath = os.path.join(dirpath, fn)
            try:
                with bpy.data.libraries.load(filepath) as (data_from, data_to):
                    for group_name in data_from.node_groups:
                        if not group_name.startswith("_"):
                            node_cache.append((group_name, filepath))
            except Exception:
                # Skip files that can't be opened
                continue

    node_cache = sorted(node_cache)

    # Update the appropriate cache
    if ui_type == "GeometryNodeTree":
        node_template_cache._node_cache_geometry = node_cache
        node_template_cache._node_cache_geometry_path = dirpath
    elif ui_type == "ShaderNodeTree":
        node_template_cache._node_cache_shader = node_cache
        node_template_cache._node_cache_shader_path = dirpath
    elif ui_type == "CompositorNodeTree":
        node_template_cache._node_cache_compositing = node_cache
        node_template_cache._node_cache_compositing_path = dirpath
    elif ui_type == "TextureNodeTree":
        node_template_cache._node_cache_texture = node_cache
        node_template_cache._node_cache_texture_path = dirpath

    return node_cache


# Initialize cache variables
node_template_cache._node_cache_geometry = []
node_template_cache._node_cache_geometry_path = ""
node_template_cache._node_cache_shader = []
node_template_cache._node_cache_shader_path = ""
node_template_cache._node_cache_compositing = []
node_template_cache._node_cache_compositing_path = ""
node_template_cache._node_cache_texture = []
node_template_cache._node_cache_texture_path = ""


class NODE_MT_template_add(Menu):
    bl_label = "Node Template"

    def draw(self, context):
        layout = self.layout
        ui_type = get_ui_type_from_context(context)
        
        if not ui_type:
            layout.label(text="Not available in this context")
            return

        dirpath = node_search_path(context, ui_type)
        if not dirpath or dirpath == "":
            layout.label(text="Set search dir in the addon-prefs")
            return

        if not os.path.exists(dirpath):
            layout.label(text="Directory doesn't exist", icon='ERROR')
            return

        try:
            node_items = node_template_cache(context)
            if not node_items:
                layout.label(text="No templates found in directory")
                return
                
            for group_name, filepath in node_items:
                props = layout.operator(
                    NODE_OT_template_add.bl_idname,
                    text=group_name,
                )
                props.filepath = filepath
                props.group_name = group_name
                
        except Exception as ex:
            layout.label(text=repr(ex), icon='ERROR')


def add_node_button(self, context):
    self.layout.menu(
        NODE_MT_template_add.__name__,
        text="longiyNodes",
        icon='FUND',
    )


classes = (
    NODE_OT_template_add,
    NODE_MT_template_add,
    NodeTemplatePrefs
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.NODE_MT_add.append(add_node_button)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.NODE_MT_add.remove(add_node_button)


if __name__ == "__main__":
    register()
