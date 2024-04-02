"""Blender plugin to import data via cloud-volume.

Copyright (C) Philipp Schlegel, 2022.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import bpy

import numpy as np
import cloudvolume as cv

from bpy.types import Panel, Operator, AddonPreferences
from bpy.props import (StringProperty,
                       BoolProperty, EnumProperty, IntProperty)
from bpy_extras.io_utils import orientation_helper, axis_conversion
from mathutils import Matrix


########################################
#  Settings
########################################


bl_info = {
 "name": "Cloudblender",
 "author": "Philipp Schlegel",
 "version": (0, 1, 0),
 "blender": (2, 80, 0),  # this MUST be 2.80.0 (i.e. not 2.9x)
 "location": "View3D > Sidebar (N) > CATMAID",
 "description": "Imports data via cloud-volume",
 "warning": "",
 "wiki_url": "",
 "tracker_url": "",
 "category": "Object"}

VOLUME_IMG = None
VOLUME_SEG = None

########################################
#  UI Elements
########################################


class CLOUDBLENDER_PT_import_panel(Panel):
    """Creates import menu in viewport side menu."""

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_label = "Import"
    bl_category = "CloudBlender"

    def draw(self, context):
        layout = self.layout

        ver_str = '.'.join([str(i) for i in bl_info['version']])
        layout.label(text=f'CloudBlender v{ver_str}')

        layout.label(text='Setup')
        box = layout.box()
        row = box.row(align=True)
        row.alignment = 'EXPAND'
        row.operator("cloudblender.connect", text="Connect", icon='OUTLINER_DATA_CURVE')

        layout.label(text='Image')
        box = layout.box()
        row = box.row(align=True)
        row.alignment = 'EXPAND'
        row.operator("cloudblender.fetch_slices", text="Fetch slices", icon='IMAGE_DATA')

        row = box.row(align=True)
        row.alignment = 'EXPAND'
        row.operator("cloudblender.fetch_cube", text="Fetch cube", icon='MESH_CUBE')

        layout.label(text='Segmentation')
        box = layout.box()
        row = box.row(align=True)
        row.alignment = 'EXPAND'
        row.operator("cloudblender.fetch_mesh", text="Fetch meshes", icon='IMAGE_DATA')

        row = box.row(align=True)
        row.alignment = 'EXPAND'
        row.operator("cloudblender.fetch_skeleton", text="Fetch skeletons", icon='IMAGE_DATA')


########################################
#  Operators
########################################


class CLOUDBLENDER_OP_connect(Operator):
    bl_idname = "cloudblender.connect"
    bl_label = 'Connect to server'
    bl_description = "Connect to server"

    server_img: StringProperty(name="Images",
                               description="Server URL for image data. Must include protocol (e.g. precomputed://...)")
    server_seg: StringProperty(name="Segmentation",
                               description="Server URL for segmentation data. Must include protocol (e.g. precomputed://...)")
    max_threads: IntProperty(name='Max Threads',
                             min=1,
                             description='Max number of parallel threads.')
    use_https: BoolProperty(name='Use HTTPs',
                            default=True)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, "server_img")
        row = layout.row(align=True)
        row.prop(self, "server_seg")
        row = layout.row(align=False)
        row.prop(self, "max_threads")
        row = layout.row(align=False)
        row.prop(self, "use_https")
        layout.label(text="Use Addon preferences to set persistent server url, credentials, etc.")

    def invoke(self, context, event):
        self.server_img = get_pref('server_img', 'precomputed://https://bossdb-open-data.s3.amazonaws.com/iarpa_microns/minnie/minnie65/em')
        self.server_seg = get_pref('server_seg', 'precomputed://gs://iarpa_microns/minnie/minnie65/seg')
        self.max_threads = get_pref('max_threads', 10)
        self.use_https = get_pref('use_https', True)
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        global VOLUME_IMG
        if self.server_img:
            print('Connecting to image server')
            print('URL: %s' % self.server_img)

            VOLUME_IMG = cv.CloudVolume(self.server_img,
                                        progress=True,
                                        use_https=self.use_https,
                                        parallel=self.max_threads)
        else:
            VOLUME_IMG = None

        global VOLUME_SEG
        if self.server_img:
            print('Connecting to segmentation server')
            print('URL: %s' % self.server_img)

            VOLUME_SEG = cv.CloudVolume(self.server_seg,
                                        progress=True,
                                        use_https=self.use_https,
                                        parallel=self.max_threads)
        else:
            VOLUME_SEG = None


        return {'FINISHED'}



class CLOUDBLENDER_OP_fetch_slices(Operator):
    """Fetch data as slices."""
    bl_idname = "cloudblender.fetch_slices"
    bl_label = 'Fetch slices'
    bl_description = "Fetch individual slices"

    x1: IntProperty(name="x1",
                    default=175000 // 2,  # goes from 4nm to 8nm voxels
                    description="")
    x2: IntProperty(name="x2",
                    default=175000 // 2 + 1000, # goes from 4nm to 8nm voxels
                    description="")
    y1: IntProperty(name="y1",
                    default=212000 // 2,
                    description="")
    y2: IntProperty(name="y2",
                    default=212000 // 2 + 1000, # goes from 4nm to 8nm voxels
                    description="")
    z1: IntProperty(name="z1",
                    default=21520, # stays at 40nm voxels
                    description="")
    z2: IntProperty(name="z2",
                    default=21520 + 1, # stays at 40nm voxels
                    description="")

    coords: EnumProperty(name='Coordinates',
                         items=[('REAL', 'Real world units','Physical units (e.g.nm)'),
                                ('VOXELS', 'Voxels', 'Voxel coordinates.')],
                         default='VOXELS',
                         description='Coordinates in which x1, x2, ... are provided.')
    mip: IntProperty(name='MIP',
                     default=0, min=0,
                     description='Level of detail (0 = max).')
    axis: EnumProperty(name='Slice axis',
                       items=[('x', 'X', 'Import slices along x-axis'),
                              ('y', 'Y', 'Import slices along y-axis'),
                              ('z', 'Z', 'Import slices along z-axis')],
                       default='z',
                       description='Axis along which to generate individual slices.')
    overwrite_material: BoolProperty(name='Overwrite materials',
                                     default=False)
    shader: EnumProperty(name='Shader',
                        items=[('PRINCIPLED', 'PRINCIPLED', 'PRINCIPLED'),
                               ('SHADELESS', 'SHADELESS', 'SHADELESS')],
                        default='PRINCIPLED',
                        description='Shader for texture material.')

    # ATTENTION:
    # using check() in an operator that uses threads, will lead to segmentation faults!
    def check(self, context):
        return True

    @classmethod
    def poll(cls, context):
        if VOLUME_IMG:
            return True
        else:
            return False

    def draw(self, context):
        scale = VOLUME_IMG.meta.scale(self.mip)
        lower_bounds = np.array(scale['voxel_offset'])
        upper_bounds = np.array(scale['size']) + lower_bounds

        layout = self.layout

        box = layout.box()
        row = box.row(align=False)
        row.prop(self, "x1")
        row.prop(self, "x2")
        row = box.row(align=False)
        row.label(text=f"Min: {lower_bounds[0]}")
        row.label(text=f"Max: {upper_bounds[0]}")
        row = box.row(align=False)
        row.prop(self, "y1")
        row.prop(self, "y2")
        row = box.row(align=False)
        row.label(text=f"Min: {lower_bounds[1]}")
        row.label(text=f"Max: {upper_bounds[1]}")
        row = box.row(align=False)
        row.prop(self, "z1")
        row.prop(self, "z2")
        row = box.row(align=False)
        row.label(text=f"Min: {lower_bounds[2]}")
        row.label(text=f"Max: {upper_bounds[2]}")

        layout.label(text="Import Options")
        box = layout.box()
        row = box.row(align=False)
        row.prop(self, "coords")
        row = box.row(align=False)
        row.prop(self, "axis")
        row = box.row(align=False)
        row.prop(self, "mip")

        scale = VOLUME_IMG.meta.scale(self.mip)
        res = ' x '.join(np.array(scale['resolution']).astype(str))
        row = box.row(align=False)
        row.label(text=f"Voxel res: {res}")

        row = box.row(align=False)
        row.prop(self, "shader")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        VOLUME_IMG.mip = self.mip
        self.resolution = VOLUME_IMG.scales[self.mip]['resolution']

        self.axis_ix = {'x': 0,
                        'y': 1,
                        'z': 2}[self.axis]

        # Make sure we're working with voxel coordinates
        if self.coords == 'REAL':
            self.x1_vxl = self.x1 // self.resolution[0]
            self.x2_vxl = self.x2 // self.resolution[0]

            self.y1_vxl = self.y1 // self.resolution[1]
            self.y2_vxl = self.y2 // self.resolution[1]

            self.z1_vxl = self.z1 // self.resolution[2]
            self.z2_vxl = self.z2 // self.resolution[2]
        else:
            self.x1_vxl = self.x1
            self.x2_vxl = self.x2

            self.y1_vxl = self.y1
            self.y2_vxl = self.y2

            self.z1_vxl = self.z1
            self.z2_vxl = self.z2

        if self.x1_vxl == self.x2_vxl:
            self.x2_vxl += 1
        if self.y1_vxl == self.y2_vxl:
            self.y2_vxl += 1
        if self.z1_vxl == self.z2_vxl:
            self.z2_vxl += 1

        # Fetch the data
        data = VOLUME_IMG[self.x1_vxl: self.x2_vxl,
                      self.y1_vxl: self.y2_vxl,
                      self.z1_vxl: self.z2_vxl]
        data = np.array(data)

        # This won't work in edit mode
        editmode = context.preferences.edit.use_enter_edit_mode
        context.preferences.edit.use_enter_edit_mode = False
        if context.active_object and context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        if self.axis == 'x':
            depth_offset = self.x1_vxl
        elif self.axis == 'y':
            depth_offset = self.y1_vxl
        elif self.axis == 'z':
            depth_offset = self.z1_vxl

        # Add slices one by one
        for i in range(data.shape[self.axis_ix]):
            if self.axis == 'x':
                slice = data[i]
            elif self.axis == 'y':
                slice = data[:, i]
            elif self.axis == 'z':
                slice = data[:, :, i]

            print(f'Importing slice {i + 1}')
            self.import_slice(slice, context, depth=depth_offset + i)

        context.preferences.edit.use_enter_edit_mode = editmode

        return {'FINISHED'}

    def import_slice(self, slice, context, depth):
        # Create material
        material = self.create_cycles_material(context, slice)

        # Create and position plane object
        plane = self.create_image_plane(context, material.name, slice, depth)

        # Assign Material
        plane.data.materials.append(material)

    def create_cycles_material(self, context, image):
        material = None
        name = f'{self.x1}_{self.x2}_{self.y1}_{self.y2}_{self.z1}_{self.z2}_mip{self.mip}'
        if self.overwrite_material:
            for mat in bpy.data.materials:
                if mat.name == name:
                    material = mat
        if not material:
            material = bpy.data.materials.new(name=name)

        material.use_nodes = True
        node_tree = material.node_tree
        out_node = clean_node_tree(node_tree)

        tex_image = self.create_cycles_texnode(context, node_tree, image)

        if self.shader == 'PRINCIPLED':
            core_shader = node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        elif self.shader == 'SHADELESS':
            core_shader = get_shadeless_node(node_tree)

        cont_bright = node_tree.nodes.new('ShaderNodeBrightContrast')
        cont_bright.inputs[2].default_value = .5

        # Connect color from texture
        node_tree.links.new(cont_bright.inputs[0], tex_image.outputs['Color'])
        node_tree.links.new(core_shader.inputs[0], cont_bright.outputs['Color'])
        node_tree.links.new(out_node.inputs['Surface'], core_shader.outputs[0])

        auto_align_nodes(node_tree)
        return material

    # Cycles/Eevee
    def create_cycles_texnode(self, context, node_tree, image):
        image_src = bpy.data.images.new('src', image.shape[0], image.shape[1])

        # Normalize image
        if VOLUME_IMG.meta.layer_type == 'image':
            image = image / np.iinfo(VOLUME_IMG.meta.dtype).max

        # Need to invert the image rows
        image = image[::-1, ::-1]

        image_channeled = np.ones(len(image_src.pixels), dtype=np.float64)
        for i in range(3):
            image_channeled[i::4] = image.flatten(order='F')
        image_src.pixels[:] = image_channeled
        #image_src.source = 'FILE'
        image_src.update()

        tex_image = node_tree.nodes.new('ShaderNodeTexImage')
        tex_image.image = image_src
        tex_image.extension = 'CLIP'
        tex_image.show_texture = True
        return tex_image

    # -------------------------------------------------------------------------
    # Geometry Creation
    def create_image_plane(self, context, name, image, depth):
        # Generate the plane
        if self.axis == 'x':
            vertices = np.array([
                                 [depth, self.y1_vxl, self.z1_vxl],
                                 [depth, self.y2_vxl, self.z1_vxl],
                                 [depth, self.y2_vxl, self.z2_vxl],
                                 [depth, self.y1_vxl, self.z2_vxl],
                                 ])
        elif self.axis == 'y':
            vertices = np.array([
                                 [self.x1_vxl, depth, self.z1_vxl],
                                 [self.x2_vxl, depth, self.z1_vxl],
                                 [self.x2_vxl, depth, self.z2_vxl],
                                 [self.x1_vxl, depth, self.z2_vxl],
                                 ])
        elif self.axis == 'z':
            vertices = np.array([
                                 [self.x1_vxl, self.y1_vxl, depth],
                                 [self.x2_vxl, self.y1_vxl, depth],
                                 [self.x2_vxl, self.y2_vxl, depth],
                                 [self.x1_vxl, self.y2_vxl, depth],
                                 ])

        # Convert to real units and then scale down
        vertices = vertices * self.resolution / get_pref('scale_factor',  10_000)

        faces = np.array([[0, 1, 2, 3]])

        new_mesh = bpy.data.meshes.new(name + '_mesh')
        new_mesh.from_pydata(vertices, [], faces)
        new_mesh.update()

        plane = bpy.data.objects.new(name, new_mesh)

        if 'slices' in bpy.data.collections:
            slice_coll = bpy.data.collections['slices']
        else:
            slice_coll = bpy.data.collections.new('slices')
            bpy.context.scene.collection.children.link(slice_coll)

        slice_coll.objects.link(plane)

        # Create UV map
        bpy.context.view_layer.objects.active = plane
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001)
        bpy.ops.object.mode_set(mode='OBJECT')

        # The UV unwrap works well if the image has the same resolution
        # across all dimensions but fails if it doesn't.
        for i, v in enumerate([(1, 1), (0, 1), (0, 0), (1, 0)]):
            plane.data.uv_layers.active.data[i].uv = v

        return plane


class CLOUDBLENDER_OP_fetch_cube(Operator):
    """Fetch data as cube."""
    bl_idname = "cloudblender.fetch_cube"
    bl_label = 'Fetch cube'
    bl_description = "Fetch slices making up a cubic volume."

    x1: IntProperty(name="x1",
                    default=175000 // 2,  # goes from 4nm to 8nm voxels
                    description="")
    x2: IntProperty(name="x2",
                    default=175000 // 2 + 1000, # goes from 4nm to 8nm voxels
                    description="")
    y1: IntProperty(name="y1",
                    default=212000 // 2,
                    description="")
    y2: IntProperty(name="y2",
                    default=212000 // 2 + 1000, # goes from 4nm to 8nm voxels
                    description="")
    z1: IntProperty(name="z1",
                    default=21320, # stays at 40nm voxels
                    description="")
    z2: IntProperty(name="z2",
                    default=21520, # stays at 40nm voxels
                    description="")

    coords: EnumProperty(name='Coordinates',
                         items=[('REAL', 'Real physical units','Real units (e.g.nm)'),
                                ('VOXELS', 'Voxels', 'Voxel coordinates.')],
                         default='VOXELS',
                         description='Coordinates in which x1, x2, ... are provided.')
    mip: IntProperty(name='MIP',
                     default=0, min=0,
                     description='Level of detail (0 = max).')
    overwrite_material: BoolProperty(name='Overwrite materials',
                                     default=False)
    shader: EnumProperty(name='Shader',
                        items=[('PRINCIPLED', 'PRINCIPLED', 'PRINCIPLED'),
                               ('SHADELESS', 'SHADELESS', 'SHADELESS')],
                        default='PRINCIPLED',
                        description='Shader for texture material.')

    # ATTENTION:
    # using check() in an operator that uses threads, will lead to segmentation faults!
    def check(self, context):
        return True

    @classmethod
    def poll(cls, context):
        if VOLUME_IMG:
            return True
        else:
            return False

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        row = box.row(align=False)
        row.prop(self, "x1")
        row.prop(self, "x2")
        row = box.row(align=False)
        row.prop(self, "y1")
        row.prop(self, "y2")
        row = box.row(align=False)
        row.prop(self, "z1")
        row.prop(self, "z2")

        layout.label(text="Import Options")
        box = layout.box()
        row = box.row(align=False)
        row.prop(self, "coords")
        row = box.row(align=False)
        row.prop(self, "mip")
        row = box.row(align=False)
        res = ' x '.join(np.array(VOLUME_IMG.meta.scale(self.mip)['resolution']).astype(str))
        row.label(text=f"Voxel res: {res}")

        row = box.row(align=False)
        row.prop(self, "shader")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):

        # Top panel
        bpy.ops.cloudblender.fetch_slices(x1=self.x1,
                                          x2=self.x2,
                                          y1=self.y1,
                                          y2=self.y2,
                                          z1=self.z1,
                                          z2=self.z1 + 1,
                                          mip=self.mip,
                                          coords=self.coords,
                                          shader=self.shader,
                                          overwrite_material=self.overwrite_material,
                                          axis='z'
                                          )
        # Bottom
        bpy.ops.cloudblender.fetch_slices(x1=self.x1,
                                          x2=self.x2,
                                          y1=self.y1,
                                          y2=self.y2,
                                          z1=self.z2 - 1,
                                          z2=self.z2,
                                          mip=self.mip,
                                          coords=self.coords,
                                          shader=self.shader,
                                          overwrite_material=self.overwrite_material,
                                          axis='z'
                                          )

        # Left
        bpy.ops.cloudblender.fetch_slices(x1=self.x1,
                                          x2=self.x2,
                                          y1=self.y1,
                                          y2=self.y1 + 1,
                                          z1=self.z1,
                                          z2=self.z2,
                                          mip=self.mip,
                                          coords=self.coords,
                                          shader=self.shader,
                                          overwrite_material=self.overwrite_material,
                                          axis='y'
                                          )

        # Right
        bpy.ops.cloudblender.fetch_slices(x1=self.x1,
                                          x2=self.x2,
                                          y1=self.y2 - 1,
                                          y2=self.y2,
                                          z1=self.z1,
                                          z2=self.z2,
                                          mip=self.mip,
                                          coords=self.coords,
                                          shader=self.shader,
                                          overwrite_material=self.overwrite_material,
                                          axis='y'
                                          )

        # Front
        bpy.ops.cloudblender.fetch_slices(x1=self.x1,
                                          x2=self.x1 + 1,
                                          y1=self.y1,
                                          y2=self.y2,
                                          z1=self.z1,
                                          z2=self.z2,
                                          mip=self.mip,
                                          coords=self.coords,
                                          shader=self.shader,
                                          overwrite_material=self.overwrite_material,
                                          axis='x'
                                          )

        # Back
        bpy.ops.cloudblender.fetch_slices(x1=self.x2 - 1,
                                          x2=self.x2,
                                          y1=self.y1,
                                          y2=self.y2,
                                          z1=self.z1,
                                          z2=self.z2,
                                          mip=self.mip,
                                          coords=self.coords,
                                          shader=self.shader,
                                          overwrite_material=self.overwrite_material,
                                          axis='x'
                                          )

        return {'FINISHED'}


class CLOUDBLENDER_OP_fetch_mesh(Operator):
    """Fetch data as slices."""
    bl_idname = "cloudblender.fetch_mesh"
    bl_label = 'Fetch neuron mesh'
    bl_description = "Fetch meshes for neurons"

    x: StringProperty(name="ID(s)",
                      default='',
                      description="ID(s) to fetch. Multiple IDs must be "
                                  "comma- or space-separated.")
    mip: IntProperty(name='MIP',
                     default=0, min=0,
                     description='Level of detail (0 = max).')
    # ATTENTION:
    # using check() in an operator that uses threads, will lead to segmentation faults!
    def check(self, context):
        return True

    @classmethod
    def poll(cls, context):
        if VOLUME_SEG:
            return True
        else:
            return False

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        row = box.row(align=False)
        row.prop(self, "x")

        layout.label(text="Import Options")
        box = layout.box()
        row = box.row(align=False)
        row.prop(self, "mip")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        VOLUME_SEG.mip = self.mip
        self.resolution = VOLUME_SEG.scales[self.mip]['resolution']

        ids = self.x.replace(',', ' ')
        ids = [int(i) for i in ids.split(' ') if i.strip()]

        meshes = VOLUME_SEG.mesh.get(ids)

        for m in meshes:
            self.create_mesh(meshes[m], name=m)

        return {'FINISHED'}

    def create_mesh(self, mesh, name=None, mat=None, collection=None):
        """Create mesh from MeshNeuron."""
        if not name:
            name = getattr(mesh, 'name', 'neuron')

        # Make copy of vertices as we are potentially modifying them
        verts = mesh.vertices.copy()

        # Convert to Blender space
        verts = verts / get_pref('scale_factor',  10_000)
        #verts = verts[:, self.axes_order]
        #verts *= self.ax_translate

        me = bpy.data.meshes.new(f'{name} mesh')
        ob = bpy.data.objects.new(f"{name}", me)
        ob.location = (0, 0, 0)
        ob.show_name = True

        blender_verts = verts.tolist()
        me.from_pydata(list(blender_verts), [], list(mesh.faces))
        me.update()

        me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))

        if not mat:
            mat_name = (f'M{name}')
            mat = bpy.data.materials.get(mat_name,
                                         bpy.data.materials.new(mat_name))
        ob.active_material = mat

        if not collection:
            col = bpy.context.scene.collection
        elif collection in bpy.data.collections:
            col = bpy.data.collections[collection]
        else:
            col = bpy.data.collections.new(collection)
            bpy.context.scene.collection.children.link(col)

        col.objects.link(ob)


########################################
#  Utilities
########################################


def apply_global_xforms(points, inverse=False):
    """Apply globally defined transforms to coordinates."""
    global_scale = 1 / get_pref('scale_factor', 10_000)
    up = get_pref('axis_up', 'Z')
    forward = get_pref('axis_forward', 'Y')

    # Note: `Matrix` is available at global namespace in Blender
    global_matrix = axis_conversion(from_forward=forward,
                                    from_up=up,
                                    ).to_4x4() @ Matrix.Scale(global_scale, 4)

    if inverse:
        global_matrix = np.linalg.inv(global_matrix)

    # Add a fourth column to points
    points_mat = np.ones((points.shape[0], 4))
    points_mat[:, :3] = points

    return np.dot(global_matrix, points_mat.T).T[:, :3]


def get_pref(key, default=None):
    """Fetch given key from preferences."""
    if 'CLOUDBLENDER' in bpy.context.preferences.addons:
        prefs = bpy.context.preferences.addons['CLOUDBLENDER'].preferences

        if hasattr(prefs, key):
            return getattr(prefs, key)
        elif default:
            return default
        else:
            raise KeyError(f'`CLOUDBLENDER` has no preference "{key}"')
    else:
        if not isinstance(default, type(None)):
            return default
        else:
            raise KeyError(f'Could not find `CLOUDBLENDER` preferences.')


def clean_node_tree(node_tree):
    """Clear all nodes in a shader node tree except the output.

    Returns the output node
    """
    nodes = node_tree.nodes
    for node in list(nodes):  # copy to avoid altering the loop's data source
        if not node.type == 'OUTPUT_MATERIAL':
            nodes.remove(node)

    return node_tree.nodes[0]


def get_input_nodes(node, links):
    """Get nodes that are a inputs to the given node"""
    # Get all links going to node.
    input_links = {lnk for lnk in links if lnk.to_node == node}
    # Sort those links, get their input nodes (and avoid doubles!).
    sorted_nodes = []
    done_nodes = set()
    for socket in node.inputs:
        done_links = set()
        for link in input_links:
            nd = link.from_node
            if nd in done_nodes:
                # Node already treated!
                done_links.add(link)
            elif link.to_socket == socket:
                sorted_nodes.append(nd)
                done_links.add(link)
                done_nodes.add(nd)
        input_links -= done_links
    return sorted_nodes


def get_shadeless_node(dest_node_tree):
    """Return a "shadless" cycles/eevee node, creating a node group if nonexistent"""
    try:
        node_tree = bpy.data.node_groups['IAP_SHADELESS']

    except KeyError:
        # need to build node shadeless node group
        node_tree = bpy.data.node_groups.new('IAP_SHADELESS', 'ShaderNodeTree')
        output_node = node_tree.nodes.new('NodeGroupOutput')
        input_node = node_tree.nodes.new('NodeGroupInput')

        node_tree.outputs.new('NodeSocketShader', 'Shader')
        node_tree.inputs.new('NodeSocketColor', 'Color')

        # This could be faster as a transparent shader, but then no ambient occlusion
        diffuse_shader = node_tree.nodes.new('ShaderNodeBsdfDiffuse')
        node_tree.links.new(diffuse_shader.inputs[0], input_node.outputs[0])

        emission_shader = node_tree.nodes.new('ShaderNodeEmission')
        node_tree.links.new(emission_shader.inputs[0], input_node.outputs[0])

        light_path = node_tree.nodes.new('ShaderNodeLightPath')
        is_glossy_ray = light_path.outputs['Is Glossy Ray']
        is_shadow_ray = light_path.outputs['Is Shadow Ray']
        ray_depth = light_path.outputs['Ray Depth']
        transmission_depth = light_path.outputs['Transmission Depth']

        unrefracted_depth = node_tree.nodes.new('ShaderNodeMath')
        unrefracted_depth.operation = 'SUBTRACT'
        unrefracted_depth.label = 'Bounce Count'
        node_tree.links.new(unrefracted_depth.inputs[0], ray_depth)
        node_tree.links.new(unrefracted_depth.inputs[1], transmission_depth)

        refracted = node_tree.nodes.new('ShaderNodeMath')
        refracted.operation = 'SUBTRACT'
        refracted.label = 'Camera or Refracted'
        refracted.inputs[0].default_value = 1.0
        node_tree.links.new(refracted.inputs[1], unrefracted_depth.outputs[0])

        reflection_limit = node_tree.nodes.new('ShaderNodeMath')
        reflection_limit.operation = 'SUBTRACT'
        reflection_limit.label = 'Limit Reflections'
        reflection_limit.inputs[0].default_value = 2.0
        node_tree.links.new(reflection_limit.inputs[1], ray_depth)

        camera_reflected = node_tree.nodes.new('ShaderNodeMath')
        camera_reflected.operation = 'MULTIPLY'
        camera_reflected.label = 'Camera Ray to Glossy'
        node_tree.links.new(camera_reflected.inputs[0], reflection_limit.outputs[0])
        node_tree.links.new(camera_reflected.inputs[1], is_glossy_ray)

        shadow_or_reflect = node_tree.nodes.new('ShaderNodeMath')
        shadow_or_reflect.operation = 'MAXIMUM'
        shadow_or_reflect.label = 'Shadow or Reflection?'
        node_tree.links.new(shadow_or_reflect.inputs[0], camera_reflected.outputs[0])
        node_tree.links.new(shadow_or_reflect.inputs[1], is_shadow_ray)

        shadow_or_reflect_or_refract = node_tree.nodes.new('ShaderNodeMath')
        shadow_or_reflect_or_refract.operation = 'MAXIMUM'
        shadow_or_reflect_or_refract.label = 'Shadow, Reflect or Refract?'
        node_tree.links.new(shadow_or_reflect_or_refract.inputs[0], shadow_or_reflect.outputs[0])
        node_tree.links.new(shadow_or_reflect_or_refract.inputs[1], refracted.outputs[0])

        mix_shader = node_tree.nodes.new('ShaderNodeMixShader')
        node_tree.links.new(mix_shader.inputs[0], shadow_or_reflect_or_refract.outputs[0])
        node_tree.links.new(mix_shader.inputs[1], diffuse_shader.outputs[0])
        node_tree.links.new(mix_shader.inputs[2], emission_shader.outputs[0])

        node_tree.links.new(output_node.inputs[0], mix_shader.outputs[0])

        auto_align_nodes(node_tree)

    group_node = dest_node_tree.nodes.new("ShaderNodeGroup")
    group_node.node_tree = node_tree

    return group_node


def auto_align_nodes(node_tree):
    """Given a shader node tree, arrange nodes neatly relative to the output node."""
    x_gap = 200
    y_gap = 180
    nodes = node_tree.nodes
    links = node_tree.links
    output_node = None
    for node in nodes:
        if node.type == 'OUTPUT_MATERIAL' or node.type == 'GROUP_OUTPUT':
            output_node = node
            break

    else:  # Just in case there is no output
        return


########################################
#  Preferences
########################################


@orientation_helper(axis_forward='-Z', axis_up='-Y')
class CLOUDBLENDER_preferences(AddonPreferences):
    bl_idname = 'CLOUDBLENDER'

    server_url: StringProperty(name="Server URL",
                               default='precomputed://https://bossdb-open-data.s3.amazonaws.com/iarpa_microns/minnie/minnie65/em')
    use_https:  BoolProperty(name="Use https", default=True)
    api_token:  StringProperty(name="API Token", default='', subtype='PASSWORD')
    max_threads: IntProperty(name="Max parallel requests",
                             default=10, min=1,
                            description='Restricting the number of parallel '
                                        'requests can help if you get errors '
                                        'when loading loads of neurons.')
    scale_factor: IntProperty(name="Conversion factor to Blender units",
                              default=10_000,
                              description='Volume units will be divided '
                                          'by this factor when imported '
                                          'into Blender.')

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.prop(self, "server_url")
        box.prop(self, "api_token")

        box = layout.box()
        box.label(text="Connection settings:")
        box.prop(self, "max_requests")

        box = layout.box()
        box.label(text="Import options:")
        box.prop(self, "scale_factor")
        box.prop(self, "axis_forward")
        box.prop(self, "axis_up")


########################################
#  Registration stuff
########################################


classes = (CLOUDBLENDER_PT_import_panel,
           CLOUDBLENDER_OP_connect,
           CLOUDBLENDER_OP_fetch_slices,
           CLOUDBLENDER_OP_fetch_cube,
           CLOUDBLENDER_OP_fetch_mesh,
           CLOUDBLENDER_preferences)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)


# This allows us to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()
