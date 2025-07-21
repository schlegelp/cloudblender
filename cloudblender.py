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

import sys
import bpy
import site
import colorsys
import fastremap
import subprocess

import numpy as np

from bpy.types import Panel, Operator, AddonPreferences
from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
    IntProperty,
    FloatProperty,
)
from bpy_extras.io_utils import orientation_helper, axis_conversion
from mathutils import Matrix, Vector


def get_blender_python_path():
    """Get the path to Blender's Python executable."""
    return sys.executable


def get_modules_path():
    """Get the path to Blender's Python modules directory."""
    return bpy.utils.user_resource("SCRIPTS", path="modules", create=True)


def append_modules_to_sys_path(modules_path):
    """Append the modules path to sys.path and add it to site."""
    if modules_path not in sys.path:
        sys.path.append(modules_path)
    site.addsitedir(modules_path)


def install_package(package, modules_path):
    """Install a package using Blender's Python executable."""
    subprocess.check_call(
        [
            get_blender_python_path(),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--target",
            modules_path,
            package,
        ]
    )


def display_message(message, title="Notification", icon="INFO"):
    """Show a popup message in Blender."""

    def draw(self, context):
        self.layout.label(text=message)

    def show_popup():
        bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)
        return None  # Stops timer

    bpy.app.timers.register(show_popup)


# Setup for loadings/installing cloudvolume
modules_path = get_modules_path()
append_modules_to_sys_path(modules_path)

try:
    import cloudvolume as cv
except ModuleNotFoundError:
    cv = None

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
    "category": "Object",
}

VOLUME_IMG = None
VOLUME_SEG = None

########################################
#  UI Elements
########################################


class CLOUDBLENDER_PT_import_panel(Panel):
    """Creates import menu in viewport side menu."""

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Import"
    bl_category = "CloudBlender"

    def draw(self, context):
        layout = self.layout

        ver_str = ".".join([str(i) for i in bl_info["version"]])
        layout.label(text=f"CloudBlender v{ver_str}")

        layout.label(text="Setup")

        if cv is None:
            box = layout.box()
            row = box.row(align=True)
            row.alignment = "EXPAND"
            row.operator(
                "cloudblender.install",
                text="Install cloud-volume",
                icon="PACKAGE",
            )

        box = layout.box()
        row = box.row(align=True)
        row.alignment = "EXPAND"
        row.operator("cloudblender.connect", text="Connect", icon="OUTLINER_DATA_CURVE")

        layout.label(text="Volume")
        box = layout.box()
        row = box.row(align=True)
        row.alignment = "EXPAND"
        row.operator("cloudblender.show_bounds", text="Show bounds", icon="CUBE")

        layout.label(text="Images")
        box = layout.box()
        row = box.row(align=True)
        row.alignment = "EXPAND"
        row.operator(
            "cloudblender.fetch_slices", text="Generate slice(s)", icon="IMAGE_DATA"
        )

        row = box.row(align=True)
        row.alignment = "EXPAND"
        row.operator("cloudblender.fetch_cube", text="Generate cube", icon="META_CUBE")

        row = box.row(align=True)
        row.alignment = "EXPAND"
        row.operator(
            "cloudblender.update_images",
            text="Update images",
            icon="ORIENTATION_PARENT",
        )

        layout.label(text="Neurons")
        box = layout.box()
        row = box.row(align=True)
        row.alignment = "EXPAND"
        row.operator("cloudblender.fetch_mesh", text="Load meshes", icon="IMAGE_DATA")

        box = layout.box()
        row = box.row(align=True)
        row.alignment = "EXPAND"
        row.operator("cloudblender.color_neurons", text="Color neurons", icon="COLOR")

        # row = box.row(align=True)
        # row.alignment = 'EXPAND'
        # row.operator("cloudblender.fetch_skeleton", text="Fetch skeletons", icon='IMAGE_DATA')


########################################
#  Operators
########################################


class CLOUDBLENDER_OP_install(Operator):
    bl_idname = "cloudblender.install"
    bl_label = "Installation"
    bl_description = "Install cloud-volume and other required packages"

    def execute(self, context):
        global cv

        install_package("cloud-volume", modules_path)

        import cloudvolume

        cv = cloudvolume

        display_message(
            "Cloud-volume installed successfully!",
        )

        return {"FINISHED"}


class CLOUDBLENDER_OP_connect(Operator):
    bl_idname = "cloudblender.connect"
    bl_label = "Connect to server"
    bl_description = "Connect to server"

    server_img: StringProperty(
        name="Images",
        description="Server URL for image data. Must include format + protocol (e.g. precomputed://https://...)",
    )
    server_seg: StringProperty(
        name="Segmentation",
        description="Server URL for segmentation data. Must include format + protocol (e.g. precomputed://https://...)",
    )
    max_threads: IntProperty(
        name="Max Threads", min=1, description="Max number of parallel threads"
    )
    # Cache is stored at $HOME/.cloudvolume/cache/$PROTOCOL/$BUCKET/$DATASET/$LAYER/$RESO
    use_cache: BoolProperty(
        name="Use Cache",
        description="Use cache to store data in ~/.cloudvolume/cache",
        default=True,
    )
    use_https: BoolProperty(
        name="Use HTTPs",
        default=True,
        description="Use HTTPs for data transfer (only relevant for gs:// protocol, recommended)",
    )
    save_settings: BoolProperty(
        name="Save settings", default=True, description="Save settings to preferences"
    )

    @classmethod
    def poll(cls, context):
        if cv:
            return True
        return False

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, "server_img")
        row = layout.row(align=True)
        row.prop(self, "server_seg")
        row = layout.row(align=False)
        row.prop(self, "max_threads")

        box = layout.box()
        row = box.row(align=False)
        row.prop(self, "use_cache")
        row.prop(self, "use_https")
        row.prop(self, "save_settings")

    def invoke(self, context, event):
        self.server_img = get_pref(
            "server_img",
            "precomputed://https://bossdb-open-data.s3.amazonaws.com/iarpa_microns/minnie/minnie65/em",
        )
        self.server_seg = get_pref(
            "server_seg", "precomputed://gs://iarpa_microns/minnie/minnie65/seg"
        )
        self.max_threads = get_pref("max_threads", 1)
        self.use_cache = get_pref("use_cache", True)
        self.use_https = get_pref("use_https", True)
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        global VOLUME_IMG
        if self.server_img:
            print("Connecting to image server")
            print("URL: %s" % self.server_img)

            VOLUME_IMG = cv.CloudVolume(
                self.server_img,
                progress=True,
                use_https=self.use_https,
                fill_missing=True,
                cache=self.use_cache,
                parallel=1,
            )
            VOLUME_IMG._max_threads = self.max_threads
        else:
            VOLUME_IMG = None

        global VOLUME_SEG
        if self.server_img:
            print("Connecting to segmentation server")
            print("URL: %s" % self.server_img)

            VOLUME_SEG = cv.CloudVolume(
                self.server_seg,
                progress=True,
                use_https=self.use_https,
                cache=self.use_cache,
                parallel=1,
            )
            VOLUME_SEG._max_threads = self.max_threads
        else:
            VOLUME_SEG = None

        if self.save_settings:
            set_pref("server_img", self.server_img)
            set_pref("server_seg", self.server_seg)
            set_pref("max_threads", self.max_threads)
            set_pref("use_cache", self.use_cache)
            set_pref("use_https", self.use_https)

        return {"FINISHED"}


class CLOUDBLENDER_OP_show_bounds(Operator):
    """Show (image) volume bounds."""

    bl_idname = "cloudblender.show_bounds"
    bl_label = "Show bounds"
    bl_description = "Show bounds of the image volume."

    object_type: EnumProperty(
        name="Type",
        items=[("MESH", "MESH", "MESH"), ("EMPTY", "EMPTY", "EMPTY")],
        default="EMPTY",
        description="What type of object to use.",
    )

    # ATTENTION:
    # using check() in an operator that uses threads, will lead to segmentation faults!
    def check(self, context):
        return True

    @classmethod
    def poll(cls, context):
        if not cv:
            return False
        if VOLUME_IMG:
            return True
        return False

    def draw(self, context):
        layout = self.layout

        box = layout.box()

        row = box.row(align=False)
        row.prop(self, "object_type")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        # Get size and offset
        size = (
            np.array(VOLUME_IMG.scales[0]["size"])
            * VOLUME_IMG.scales[0]["resolution"]
            / get_pref("scale_factor", 10_000)
        )
        offset = (
            np.array(VOLUME_IMG.scales[0]["voxel_offset"])
            * VOLUME_IMG.scales[0]["resolution"]
            / get_pref("scale_factor", 10_000)
        )

        if self.object_type == "MESH":
            bpy.ops.mesh.primitive_cube_add(size=1)
        else:
            bpy.ops.object.empty_add(type="CUBE", align="WORLD")

        ob = bpy.context.active_object
        ob.name = "VolumeBounds"
        ob.location = offset + size / 2
        ob.scale = size / 2

        return {"FINISHED"}


class CLOUDBLENDER_OP_fetch_slices(Operator):
    """Fetch data as slices."""

    bl_idname = "cloudblender.fetch_slices"
    bl_label = "Fetch slices"
    bl_description = "Fetch individual slices"

    x1: IntProperty(
        name="x1",
        default=87500,
        description="",
    )
    x2: IntProperty(
        name="x2",
        default=87500 + 1000,
        description="",
    )
    y1: IntProperty(
        name="y1",
        default=212000 // 2,
        description="",
    )
    y2: IntProperty(
        name="y2",
        default=212000 // 2 + 1000,
        description="",
    )
    z1: IntProperty(
        name="z1",
        default=21520,
        description="",
    )
    z2: IntProperty(
        name="z2",
        default=21520 + 1,
        description="",
    )
    coords: EnumProperty(
        name="Coordinates",
        items=[
            ("REAL", "Real world units", "Physical units (e.g.nm)"),
            ("VOXELS", "Voxels", "Voxel coordinates."),
        ],
        default="VOXELS",
        description="Coordinates in which x1, x2, ... are provided.",
    )
    blend_seg: BoolProperty(
        name="Overlay segmentation",
        default=True,
        description="Whether to overlay the segmentation. Ignored if no segmentation configured.",
    )
    mip: IntProperty(
        name="MIP", default=0, min=0, description="Level of detail (0 = max)."
    )
    axis: EnumProperty(
        name="Slice axis",
        items=[
            ("x", "X", "Import slices along x-axis"),
            ("y", "Y", "Import slices along y-axis"),
            ("z", "Z", "Import slices along z-axis"),
        ],
        default="z",
        description="Axis along which to generate individual slices.",
    )
    overwrite_material: BoolProperty(name="Overwrite materials", default=False)
    shader: EnumProperty(
        name="Shader",
        items=[
            ("PRINCIPLED", "PRINCIPLED", "PRINCIPLED"),
            ("SHADELESS", "SHADELESS", "SHADELESS"),
        ],
        default="PRINCIPLED",
        description="Shader for texture material.",
    )

    # ATTENTION:
    # using check() in an operator that uses threads, will lead to segmentation faults!
    def check(self, context):
        return True

    @classmethod
    def poll(cls, context):
        if not cv:
            return False
        if VOLUME_IMG:
            return True
        else:
            return False

    def draw(self, context):
        scale = VOLUME_IMG.meta.scale(self.mip)
        lower_bounds = np.array(scale["voxel_offset"])
        upper_bounds = np.array(scale["size"]) + lower_bounds

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
        row = box.row(align=False)
        row.prop(self, "blend_seg")

        scale = VOLUME_IMG.meta.scale(self.mip)
        res = " x ".join(np.array(scale["resolution"]).astype(str))
        row = box.row(align=False)
        row.label(text=f"Voxel res: {res}")

        row = box.row(align=False)
        row.prop(self, "shader")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        VOLUME_IMG.mip = self.mip
        self.resolution = VOLUME_IMG.scales[self.mip]["resolution"]

        self.axis_ix = {"x": 0, "y": 1, "z": 2}[self.axis]

        # Make sure we're working with voxel coordinates
        if self.coords == "REAL":
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

        # Make sure we don't have zero-sized slices
        for c in ["x", "y", "z"]:
            if getattr(self, f"{c}1_vxl") == getattr(self, f"{c}2_vxl"):
                setattr(self, f"{c}2_vxl", getattr(self, f"{c}1_vxl") + 1)

        # Fetch the data
        data = VOLUME_IMG[
            self.x1_vxl : self.x2_vxl,
            self.y1_vxl : self.y2_vxl,
            self.z1_vxl : self.z2_vxl,
        ]
        data = np.array(data)

        # Blend with segmentation data (if requested)
        if self.blend_seg and VOLUME_SEG:
            VOLUME_SEG.mip = self.mip
            self.resolution_seg = VOLUME_SEG.scales[self.mip]["resolution"]

            # Translate image voxel coordinates into segmentation coordinates
            im2seg_res_ratio = np.array(self.resolution_seg) / np.array(self.resolution)
            self.x1_vxl_seg = int(self.x1_vxl // im2seg_res_ratio[0])
            self.x2_vxl_seg = int(self.x2_vxl // im2seg_res_ratio[0])
            self.y1_vxl_seg = int(self.y1_vxl // im2seg_res_ratio[1])
            self.y2_vxl_seg = int(self.y2_vxl // im2seg_res_ratio[1])
            self.z1_vxl_seg = int(self.z1_vxl // im2seg_res_ratio[2])
            self.z2_vxl_seg = int(self.z2_vxl // im2seg_res_ratio[2])

            # Make sure we don't have zero-sized slices
            for c in ["x", "y", "z"]:
                if getattr(self, f"{c}1_vxl_seg") == getattr(self, f"{c}2_vxl_seg"):
                    setattr(self, f"{c}2_vxl_seg", getattr(self, f"{c}1_vxl_seg") + 1)

            # Get the segmentation data
            data_seg = VOLUME_SEG[
                self.x1_vxl_seg : self.x2_vxl_seg,
                self.y1_vxl_seg : self.y2_vxl_seg,
                self.z1_vxl_seg : self.z2_vxl_seg,
            ]
            # Map IDs to colors
            data_seg_rgb = seg_ids_to_colors(data_seg)
        else:
            data_seg_rgb = None

        # This won't work in edit mode
        editmode = context.preferences.edit.use_enter_edit_mode
        context.preferences.edit.use_enter_edit_mode = False
        if context.active_object and context.active_object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        if self.axis == "x":
            depth_offset = self.x1_vxl
        elif self.axis == "y":
            depth_offset = self.y1_vxl
        elif self.axis == "z":
            depth_offset = self.z1_vxl

        # Add slices one by one
        for i in range(data.shape[self.axis_ix]):
            if self.axis == "x":
                im_slice = data[i]
            elif self.axis == "y":
                im_slice = data[:, i]
            elif self.axis == "z":
                im_slice = data[:, :, i]

            # Make a flat 2d image slice
            im_slice = im_slice.reshape(im_slice.shape[0], im_slice.shape[1])

            if data_seg_rgb is not None:
                # Map image index to segmentation index
                i_seg = int(i * im2seg_res_ratio[self.axis_ix])
                if self.axis == "x":
                    seg_slice = data_seg_rgb[i_seg]
                elif self.axis == "y":
                    seg_slice = data_seg_rgb[:, i_seg]
                elif self.axis == "z":
                    seg_slice = data_seg_rgb[:, :, i_seg]

                # Make a flat 2d RGB image slice
                seg_slice = seg_slice.reshape(seg_slice.shape[0], seg_slice.shape[1], 3)
            else:
                seg_slice = None

            print(f"Importing slice {i + 1} (of {data.shape[self.axis_ix]})")
            self.import_slice(im_slice, seg_slice, context, depth=depth_offset + i)

        context.preferences.edit.use_enter_edit_mode = editmode

        return {"FINISHED"}

    def import_slice(self, im_slice, seg_slice, context, depth):
        # Create material
        material = self.create_cycles_material(context, im_slice, seg_slice)

        # Create and position plane object
        plane = self.create_image_plane(context, material.name, depth)

        # Assign Material
        plane.data.materials.append(material)

    def create_cycles_material(self, context, image, seg):
        material = None
        name = (
            f"{self.x1}_{self.x2}_{self.y1}_{self.y2}_{self.z1}_{self.z2}_mip{self.mip}"
        )
        if self.overwrite_material:
            for mat in bpy.data.materials:
                if mat.name == name:
                    material = mat
        if not material:
            material = bpy.data.materials.new(name=name)

        material.use_nodes = True
        node_tree = material.node_tree
        out_node = clean_node_tree(node_tree)

        tex_image = create_cycles_texnode(node_tree, image)

        if self.shader == "PRINCIPLED":
            core_shader = node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        elif self.shader == "SHADELESS":
            core_shader = get_shadeless_node(node_tree)

        # Brightness/Contrast node to adjust the image data
        cont_bright = node_tree.nodes.new("ShaderNodeBrightContrast")
        cont_bright.inputs[2].default_value = 0.5

        # Connect color from texture
        node_tree.links.new(cont_bright.inputs[0], tex_image.outputs["Color"])

        # If no segmentation, we can just connect the texture to the shader
        if seg is None:
            node_tree.links.new(core_shader.inputs[0], cont_bright.outputs["Color"])
        else:
            tex_seg = create_cycles_texnode(node_tree, seg)

            # Generate a mix node
            mix_node = node_tree.nodes.new("ShaderNodeMixRGB")

            # Connect both textures to the mix node
            node_tree.links.new(mix_node.inputs["Color1"], cont_bright.outputs["Color"])
            node_tree.links.new(mix_node.inputs["Color2"], tex_seg.outputs["Color"])

            # Connect mix node to shader
            node_tree.links.new(core_shader.inputs[0], mix_node.outputs["Color"])

        # Connect BSDF output to material surface
        node_tree.links.new(out_node.inputs["Surface"], core_shader.outputs[0])

        # Set the roughness to 0
        node_tree.nodes["Principled BSDF"].inputs[2].default_value = 0
        # Deactivate specular reflection
        node_tree.nodes["Principled BSDF"].inputs[12].default_value = 0

        auto_align_nodes(node_tree)
        return material

    # -------------------------------------------------------------------------
    # Geometry Creation
    def create_image_plane(self, context, name, depth):
        # Generate the plane
        if self.axis == "x":
            vertices = np.array(
                [
                    [depth, self.y1_vxl, self.z1_vxl],
                    [depth, self.y2_vxl, self.z1_vxl],
                    [depth, self.y2_vxl, self.z2_vxl],
                    [depth, self.y1_vxl, self.z2_vxl],
                ]
            )
        elif self.axis == "y":
            vertices = np.array(
                [
                    [self.x1_vxl, depth, self.z1_vxl],
                    [self.x2_vxl, depth, self.z1_vxl],
                    [self.x2_vxl, depth, self.z2_vxl],
                    [self.x1_vxl, depth, self.z2_vxl],
                ]
            )
        elif self.axis == "z":
            vertices = np.array(
                [
                    [self.x1_vxl, self.y1_vxl, depth],
                    [self.x2_vxl, self.y1_vxl, depth],
                    [self.x2_vxl, self.y2_vxl, depth],
                    [self.x1_vxl, self.y2_vxl, depth],
                ]
            )

        # Convert to real units and then scale down
        vertices = vertices * self.resolution / get_pref("scale_factor", 10_000)

        faces = np.array([[0, 1, 2, 3]])

        new_mesh = bpy.data.meshes.new(name + "_mesh")
        new_mesh.from_pydata(vertices, [], faces)
        new_mesh.update()

        plane = bpy.data.objects.new(name, new_mesh)

        # Track the slice's properties (for later updates)
        plane["mip"] = self.mip
        plane["axis"] = self.axis
        plane["depth"] = depth
        plane["shader"] = self.shader
        plane["show_seg"] = self.blend_seg
        plane["x1"] = self.x1_vxl
        plane["x2"] = self.x2_vxl
        plane["y1"] = self.y1_vxl
        plane["y2"] = self.y2_vxl
        plane["z1"] = self.z1_vxl
        plane["z2"] = self.z2_vxl

        if "slices" in bpy.data.collections:
            slice_coll = bpy.data.collections["slices"]
        else:
            slice_coll = bpy.data.collections.new("slices")
            bpy.context.scene.collection.children.link(slice_coll)

        slice_coll.objects.link(plane)

        # Create UV map
        bpy.context.view_layer.objects.active = plane
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.001)
        bpy.ops.object.mode_set(mode="OBJECT")

        # The UV unwrap works well if the image has the same resolution
        # across all dimensions but fails if it doesn't.
        for i, v in enumerate([(1, 1), (0, 1), (0, 0), (1, 0)]):
            plane.data.uv_layers.active.data[i].uv = v

        return plane


class CLOUDBLENDER_OP_fetch_cube(Operator):
    """Fetch data as cube."""

    bl_idname = "cloudblender.fetch_cube"
    bl_label = "Fetch cube"
    bl_description = "Fetch slices making up a cubic volume."

    x1: IntProperty(
        name="x1",
        default=175000 // 2,  # goes from 4nm to 8nm voxels
        description="",
    )
    x2: IntProperty(
        name="x2",
        default=175000 // 2 + 1000,  # goes from 4nm to 8nm voxels
        description="",
    )
    y1: IntProperty(name="y1", default=212000 // 2, description="")
    y2: IntProperty(
        name="y2",
        default=212000 // 2 + 1000,  # goes from 4nm to 8nm voxels
        description="",
    )
    z1: IntProperty(
        name="z1",
        default=21320,  # stays at 40nm voxels
        description="",
    )
    z2: IntProperty(
        name="z2",
        default=21520,  # stays at 40nm voxels
        description="",
    )

    coords: EnumProperty(
        name="Coordinates",
        items=[
            ("REAL", "Real physical units", "Real units (e.g.nm)"),
            ("VOXELS", "Voxels", "Voxel coordinates."),
        ],
        default="VOXELS",
        description="Coordinates in which x1, x2, ... are provided.",
    )
    blend_seg: BoolProperty(
        name="Overlay segmentation",
        default=True,
        description="Whether to overlay the segmentation. Ignored if no segmentation configured.",
    )
    mip: IntProperty(
        name="MIP", default=0, min=0, description="Level of detail (0 = max)."
    )
    overwrite_material: BoolProperty(name="Overwrite materials", default=False)
    shader: EnumProperty(
        name="Shader",
        items=[
            ("PRINCIPLED", "PRINCIPLED", "PRINCIPLED"),
            ("SHADELESS", "SHADELESS", "SHADELESS"),
        ],
        default="PRINCIPLED",
        description="Shader for texture material.",
    )

    # ATTENTION:
    # using check() in an operator that uses threads, will lead to segmentation faults!
    def check(self, context):
        return True

    @classmethod
    def poll(cls, context):
        if not cv:
            return False
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
        row.prop(self, "blend_seg")
        row = box.row(align=False)
        res = " x ".join(
            np.array(VOLUME_IMG.meta.scale(self.mip)["resolution"]).astype(str)
        )
        row.label(text=f"Voxel res: {res}")

        row = box.row(align=False)
        row.prop(self, "shader")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        # Top panel
        bpy.ops.cloudblender.fetch_slices(
            x1=self.x1,
            x2=self.x2,
            y1=self.y1,
            y2=self.y2,
            z1=self.z1,
            z2=self.z1 + 1,
            mip=self.mip,
            blend_seg=self.blend_seg,
            coords=self.coords,
            shader=self.shader,
            overwrite_material=self.overwrite_material,
            axis="z",
        )
        # Bottom
        bpy.ops.cloudblender.fetch_slices(
            x1=self.x1,
            x2=self.x2,
            y1=self.y1,
            y2=self.y2,
            z1=self.z2 - 1,
            z2=self.z2,
            mip=self.mip,
            blend_seg=self.blend_seg,
            coords=self.coords,
            shader=self.shader,
            overwrite_material=self.overwrite_material,
            axis="z",
        )

        # Left
        bpy.ops.cloudblender.fetch_slices(
            x1=self.x1,
            x2=self.x2,
            y1=self.y1,
            y2=self.y1 + 1,
            z1=self.z1,
            z2=self.z2,
            mip=self.mip,
            blend_seg=self.blend_seg,
            coords=self.coords,
            shader=self.shader,
            overwrite_material=self.overwrite_material,
            axis="y",
        )

        # Right
        bpy.ops.cloudblender.fetch_slices(
            x1=self.x1,
            x2=self.x2,
            y1=self.y2 - 1,
            y2=self.y2,
            z1=self.z1,
            z2=self.z2,
            mip=self.mip,
            blend_seg=self.blend_seg,
            coords=self.coords,
            shader=self.shader,
            overwrite_material=self.overwrite_material,
            axis="y",
        )

        # Front
        bpy.ops.cloudblender.fetch_slices(
            x1=self.x1,
            x2=self.x1 + 1,
            y1=self.y1,
            y2=self.y2,
            z1=self.z1,
            z2=self.z2,
            mip=self.mip,
            blend_seg=self.blend_seg,
            coords=self.coords,
            shader=self.shader,
            overwrite_material=self.overwrite_material,
            axis="x",
        )

        # Back
        bpy.ops.cloudblender.fetch_slices(
            x1=self.x2 - 1,
            x2=self.x2,
            y1=self.y1,
            y2=self.y2,
            z1=self.z1,
            z2=self.z2,
            mip=self.mip,
            blend_seg=self.blend_seg,
            coords=self.coords,
            shader=self.shader,
            overwrite_material=self.overwrite_material,
            axis="x",
        )

        return {"FINISHED"}


class CLOUDBLENDER_OP_update_images(Operator):
    """Update textures image slices."""

    bl_idname = "cloudblender.update_images"
    bl_label = "Update images"
    bl_description = "Update textures of all image slices."

    # ATTENTION:
    # using check() in an operator that uses threads, will lead to segmentation faults!
    def check(self, context):
        if not cv:
            return False
        return True

    @classmethod
    def poll(cls, context):
        if VOLUME_IMG:
            return True
        else:
            return False

    def execute(self, context):
        # This won't work in edit mode
        editmode = context.preferences.edit.use_enter_edit_mode
        context.preferences.edit.use_enter_edit_mode = False
        if context.active_object and context.active_object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        for ob in bpy.data.objects:
            # If not "mip" property, skip
            if ob.get("mip", None) is None:
                continue

            print("Updating %s" % ob.name)

            # Get the properties
            self.mip = round(ob["mip"])
            self.axis = ob["axis"]
            self.depth = ob["depth"]
            self.shader = ob["shader"]

            # Get the global vertex coordinates
            coords = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])

            # Map to physical space
            coords *= get_pref("scale_factor", 10_000)

            # Map them to voxels
            coords_vxl = (
                (coords / VOLUME_IMG.scales[self.mip]["resolution"]).round().astype(int)
            )

            # Translate into slice
            self.x1_vxl = coords_vxl[:, 0].min()
            self.x2_vxl = coords_vxl[:, 0].max()
            self.y1_vxl = coords_vxl[:, 1].min()
            self.y2_vxl = coords_vxl[:, 1].max()
            self.z1_vxl = coords_vxl[:, 2].min()
            self.z2_vxl = coords_vxl[:, 2].max()
            if self.axis == "x":
                self.depth = self.x1_vxl
            elif self.axis == "y":
                self.depth = self.y1_vxl
            elif self.axis == "z":
                self.depth = self.z1_vxl

            # Make sure we don't get zero volume slices
            if self.x1_vxl == self.x2_vxl:
                self.x2_vxl += 1
            if self.y1_vxl == self.y2_vxl:
                self.y2_vxl += 1
            if self.z1_vxl == self.z2_vxl:
                self.z2_vxl += 1

            # Check if we need to update
            if (
                self.x1_vxl == ob["x1"]
                and self.x2_vxl == ob["x2"]
                and self.y1_vxl == ob["y1"]
                and self.y2_vxl == ob["y2"]
                and self.z1_vxl == ob["z1"]
                and self.z2_vxl == ob["z2"]
                and self.mip == ob.get("mip_old")
            ):
                print("  No update needed.")
                continue

            shape = (
                self.x2_vxl - self.x1_vxl,
                self.y2_vxl - self.y1_vxl,
                self.z2_vxl - self.z1_vxl,
            )
            print(
                f"  Loading data for {self.x1_vxl}:{self.x2_vxl}, {self.y1_vxl}:{self.y2_vxl}, {self.z1_vxl}:{self.z2_vxl} @ mip {self.mip} ({shape})"
            )

            # Fetch the data
            old_mip = VOLUME_IMG.mip
            VOLUME_IMG.mip = self.mip
            data = VOLUME_IMG[
                self.x1_vxl : self.x2_vxl,
                self.y1_vxl : self.y2_vxl,
                self.z1_vxl : self.z2_vxl,
            ]
            data = np.array(data)
            VOLUME_IMG.mip = old_mip

            # Extract slice
            if self.axis == "x":
                pane = data[0]
            elif self.axis == "y":
                pane = data[:, 0]
            elif self.axis == "z":
                pane = data[:, :, 0]

            pane = pane.reshape(pane.shape[0], pane.shape[1])

            if ob["show_seg"] and VOLUME_SEG:
                old_mip = VOLUME_SEG.mip
                VOLUME_SEG.mip = self.mip
                self.resolution_im = VOLUME_IMG.scales[self.mip]["resolution"]
                self.resolution_seg = VOLUME_SEG.scales[self.mip]["resolution"]

                # Translate image voxel coordinates into segmentation coordinates
                im2seg_res_ratio = np.array(self.resolution_seg) / np.array(
                    self.resolution_im
                )
                self.x1_vxl_seg = int(self.x1_vxl // im2seg_res_ratio[0])
                self.x2_vxl_seg = int(self.x2_vxl // im2seg_res_ratio[0])
                self.y1_vxl_seg = int(self.y1_vxl // im2seg_res_ratio[1])
                self.y2_vxl_seg = int(self.y2_vxl // im2seg_res_ratio[1])
                self.z1_vxl_seg = int(self.z1_vxl // im2seg_res_ratio[2])
                self.z2_vxl_seg = int(self.z2_vxl // im2seg_res_ratio[2])

                shape = (
                    self.x2_vxl_seg - self.x1_vxl_seg,
                    self.y2_vxl_seg - self.y1_vxl_seg,
                    self.z2_vxl_seg - self.z1_vxl_seg,
                )
                print(
                    f"  Loading segmentation data for {self.x1_vxl_seg}:{self.x2_vxl_seg}, {self.y1_vxl_seg}:{self.y2_vxl_seg}, {self.z1_vxl_seg}:{self.z2_vxl_seg} @ mip {self.mip} ({shape})"
                )

                # Make sure we don't have zero-sized slices
                for c in ["x", "y", "z"]:
                    if getattr(self, f"{c}1_vxl_seg") == getattr(self, f"{c}2_vxl_seg"):
                        setattr(
                            self, f"{c}2_vxl_seg", getattr(self, f"{c}1_vxl_seg") + 1
                        )

                # Get the segmentation data
                data_seg = VOLUME_SEG[
                    self.x1_vxl_seg : self.x2_vxl_seg,
                    self.y1_vxl_seg : self.y2_vxl_seg,
                    self.z1_vxl_seg : self.z2_vxl_seg,
                ]
                VOLUME_SEG.mip = old_mip

                # Map IDs to colors
                data_seg_rgb = seg_ids_to_colors(data_seg)

                # Extract slice
                if self.axis == "x":
                    pane_seg = data_seg_rgb[0]
                elif self.axis == "y":
                    pane_seg = data_seg_rgb[:, 0]
                elif self.axis == "z":
                    pane_seg = data_seg_rgb[:, :, 0]

                pane_seg = pane_seg.reshape(pane_seg.shape[0], pane_seg.shape[1], 3)
            else:
                pane_seg = None

            self.update_slice(ob, pane, pane_seg)

            # Update the slice's properties
            ob["x1"] = int(self.x1_vxl)
            ob["x2"] = int(self.x2_vxl)
            ob["y1"] = int(self.y1_vxl)
            ob["y2"] = int(self.y2_vxl)
            ob["z1"] = int(self.z1_vxl)
            ob["z2"] = int(self.z2_vxl)
            ob["mip_old"] = self.mip  # Store this mip level for later comparison

            print("  Done!")

        # Clean up unused materials
        for block in bpy.data.materials:
            if block.users == 0:
                bpy.data.materials.remove(block)
        # Clean up unused textures
        for block in bpy.data.textures:
            if block.users == 0:
                bpy.data.textures.remove(block)
        # Clean up unused images
        for block in bpy.data.images:
            if block.users == 0:
                bpy.data.images.remove(block)

        context.preferences.edit.use_enter_edit_mode = editmode

        return {"FINISHED"}

    def update_slice(self, ob, image, seg):
        # Get the material (we're assuming its the first one)
        material = ob.data.materials[0]

        # Get the node tree
        node_tree = material.node_tree

        # Parse the nodes
        out_node = core_shader = cont_bright = mix_node = None
        for node in node_tree.nodes:
            if node.type == "TEX_IMAGE":
                node_tree.nodes.remove(node)
            elif node.type == "OUTPUT_MATERIAL":
                out_node = node
            elif node.type == "BSDF_PRINCIPLED":
                core_shader = node
            elif node.type == "BRIGHTCONTRAST":
                cont_bright = node
            elif node.type == "MIX_RGB":
                mix_node = node
        if any(n is None for n in [out_node, core_shader, cont_bright]):
            raise KeyError("  Error: Expected material nodes missing.")

        # Update the texture
        tex_image = create_cycles_texnode(node_tree, image)

        # Connect color from texture
        node_tree.links.new(cont_bright.inputs[0], tex_image.outputs["Color"])

        # If no segmentation, we can just connect the texture to the shader
        if seg is None:
            node_tree.links.new(core_shader.inputs[0], cont_bright.outputs["Color"])
        else:
            tex_seg = create_cycles_texnode(node_tree, seg)

            # Connect both textures to the mix node
            node_tree.links.new(mix_node.inputs["Color1"], cont_bright.outputs["Color"])
            node_tree.links.new(mix_node.inputs["Color2"], tex_seg.outputs["Color"])

            # Connect mix node to shader
            node_tree.links.new(core_shader.inputs[0], mix_node.outputs["Color"])

        # Connect BSDF output to material surface
        node_tree.links.new(out_node.inputs["Surface"], core_shader.outputs[0])

    def update_slice2(self, ob, slice, context):
        # Remove the current material(s)
        ob.data.materials.clear()

        # New material
        material = self.create_cycles_material(context, slice)

        # Assign new material
        ob.data.materials.append(material)

    def create_cycles_material(self, context, image):
        material = None
        name = f"{self.x1_vxl}_{self.x2_vxl}_{self.y1_vxl}_{self.y2_vxl}_{self.z1_vxl}_{self.z2_vxl}_mip{self.mip}"
        material = bpy.data.materials.new(name=name)

        material.use_nodes = True
        node_tree = material.node_tree
        out_node = clean_node_tree(node_tree)

        tex_image = create_cycles_texnode(node_tree, image)

        if self.shader == "PRINCIPLED":
            core_shader = node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        elif self.shader == "SHADELESS":
            core_shader = get_shadeless_node(node_tree)

        cont_bright = node_tree.nodes.new("ShaderNodeBrightContrast")
        cont_bright.inputs[2].default_value = 0  # Contrast

        # Connect color from texture
        node_tree.links.new(cont_bright.inputs[0], tex_image.outputs["Color"])
        node_tree.links.new(core_shader.inputs[0], cont_bright.outputs["Color"])
        node_tree.links.new(out_node.inputs["Surface"], core_shader.outputs[0])

        # Set the roughness to 0
        node_tree.nodes["Principled BSDF"].inputs[2].default_value = 0
        # Deactivate specular reflection
        node_tree.nodes["Principled BSDF"].inputs[12].default_value = 0

        auto_align_nodes(node_tree)
        return material


class CLOUDBLENDER_OP_fetch_mesh(Operator):
    """Fetch data as slices."""

    bl_idname = "cloudblender.fetch_mesh"
    bl_label = "Fetch neuron mesh"
    bl_description = "Fetch meshes for neurons"

    x: StringProperty(
        name="ID(s)",
        default="",
        description="ID(s) to fetch. Multiple IDs must be comma- or space-separated.",
    )
    mip: IntProperty(
        name="MIP", default=0, min=0, description="Level of detail (0 = max)."
    )

    # ATTENTION:
    # using check() in an operator that uses threads, will lead to segmentation faults!
    def check(self, context):
        return True

    @classmethod
    def poll(cls, context):
        if not cv:
            return False
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
        self.resolution = VOLUME_SEG.scales[self.mip]["resolution"]

        ids = self.x.replace(",", " ")
        ids = [int(i) for i in ids.split(" ") if i.strip()]

        meshes = VOLUME_SEG.mesh.get(ids)

        for m in meshes:
            self.create_mesh(meshes[m], name=m)

        return {"FINISHED"}

    def create_mesh(self, mesh, name=None, mat=None, collection=None):
        """Create mesh from MeshNeuron."""
        if not name:
            name = getattr(mesh, "name", "neuron")

        # Make copy of vertices as we are potentially modifying them
        verts = mesh.vertices.copy()

        # Convert to Blender space
        verts = verts / get_pref("scale_factor", 10_000)
        # verts = verts[:, self.axes_order]
        # verts *= self.ax_translate

        me = bpy.data.meshes.new(f"{name} mesh")
        ob = bpy.data.objects.new(f"{name}", me)
        ob.location = (0, 0, 0)
        ob.show_name = True
        ob["type"] = "NEURON"
        ob["id"] = str(name)  # store ID as string (C does not like int64)

        blender_verts = verts.tolist()
        me.from_pydata(list(blender_verts), [], list(mesh.faces))
        me.update()

        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))

        if not mat:
            mat_name = f"M{name}"
            mat = bpy.data.materials.get(mat_name, bpy.data.materials.new(mat_name))
        ob.active_material = mat

        if not collection:
            col = bpy.context.scene.collection
        elif collection in bpy.data.collections:
            col = bpy.data.collections[collection]
        else:
            col = bpy.data.collections.new(collection)
            bpy.context.scene.collection.children.link(col)

        col.objects.link(ob)


class CLOUDBLENDER_OP_color_neurons(Operator):
    """Colorize neurons."""

    bl_idname = "cloudblender.color_neurons"
    bl_label = "Colorize neurons"
    bl_description = (
        "Colorize neurons - uses the same color scheme as for segmentation."
    )

    # ATTENTION:
    # using check() in an operator that uses threads, will lead to segmentation faults!
    def check(self, context):
        return True

    @classmethod
    def poll(cls, context):
        if not cv:
            return False
        return True

    def execute(self, context):
        for ob in bpy.data.objects:
            if ob.get("type") != "NEURON":
                continue
            try:
                id = int(ob["id"])
            except ValueError:
                print("Error parsing ID for object %s" % ob.name)
                continue

            color = rgb_from_segment_id(1234, id)

            mat = ob.active_material

            mat.diffuse_color[0] = color[0]
            mat.diffuse_color[1] = color[1]
            mat.diffuse_color[2] = color[2]

            if hasattr(mat, "node_tree") and "Principled BSDF" in mat.node_tree.nodes:
                # If we have a Principled BSDF, set the base color
                # This is necessary for Cycles rendering
                mat.node_tree.nodes["Principled BSDF"].inputs[0].default_value = (color[0], color[1], color[2], 1)


        return {"FINISHED"}


########################################
#  Utilities
########################################


def fit_z_plane(z_plane, camera):
    """Fit z-plane to camera's field of view."""
    # Get the four rays that define the camera's field of view
    rays = camera.data.view_frame(
        scene=bpy.context.scene
    )  # these are vectors *before* transformation

    # Get the z-coordinate of plane
    z = z_plane.location.z

    # Collect the intersection points for each ray
    # The order is: TR, BR, BL, TL
    points = []
    for ray in rays:
        p = Vector(ray_intersects_z(camera.matrix_world, ray, z))
        points.append(p)


def ray_intersects_z(matrix_world, ray_vector, z_target):
    """Get the point where a ray intersects a z-plane."""
    # Extract the world matrix components
    mw = np.array(matrix_world)  # Assuming it's a 4x4 numpy array
    ray = np.array(ray_vector)  # 3D ray vector

    # Compute transformed ray direction in world space
    transformed_ray = mw[:3, :3] @ ray  # Only consider rotation/scaling part

    # Compute the z-direction component
    z_component = transformed_ray[2]

    # Check for parallel ray
    if np.isclose(z_component, 0):
        return None  # No intersection; ray is parallel to the plane

    # Solve for d
    d = (z_target - mw[2, 3]) / z_component  # mw[2, 3] is the z-translation

    # Compute intersection point
    intersection = mw @ np.append(d * ray, 1)  # Homogeneous coordinates
    return intersection[:3]  # Return (x, y, z)


def hash_function(state, value):
    """Python implementation of hashCombine() function in src/gpu_hash/hash_function.ts.

    This is a modified murmur hash.
    """
    k1 = 0xCC9E2D51
    k2 = 0x1B873593
    state = state & 0xFFFFFFFF
    value = (value * k1) & 0xFFFFFFFF
    value = ((value << 15) | value >> 17) & 0xFFFFFFFF
    value = (value * k2) & 0xFFFFFFFF
    state = (state ^ value) & 0xFFFFFFFF
    state = ((state << 13) | state >> 19) & 0xFFFFFFFF
    state = ((state * 5) + 0xE6546B64) & 0xFFFFFFFF
    return state


def rgb_from_segment_id(color_seed, segment_id):
    """Return the RGBA for a segment given a color seed and the segment ID."""
    segment_id = int(segment_id)  # necessary since segment_id is 64 bit originally
    result = hash_function(state=color_seed, value=segment_id)
    newvalue = segment_id >> 32
    result2 = hash_function(state=result, value=newvalue)
    c0 = (result2 & 0xFF) / 255.0
    c1 = ((result2 >> 8) & 0xFF) / 255.0
    h = c0
    s = 0.5 + 0.5 * c1
    v = 1.0
    return colorsys.hsv_to_rgb(h, s, v)


def seg_ids_to_colors(seg, cmap=None, seed=1234):
    """Convert segmentation IDs to colors.

    Parameters
    ----------
    seg :   np.ndarray
            (N, M, K) array with segmentation IDs.
    cmap :  dict, optional
            Dictionary mapping IDs to RGB colors. If not provided,
            a colormap is generated deterministically.

    """
    # Get the unique IDs in the segmentation
    ids = np.unique(seg)

    print(f"  Converting {len(ids):,} segmentation IDs to RGB...")

    if not cmap:
        # Generate colors
        cmap = {i: rgb_from_segment_id(seed, i) for i in ids}

    cmap[0] = (0, 0, 0)  # Background is a dark grey

    # Convert the segmentation to RGB
    # seg_rgb = np.zeros(list(seg.shape) + [3], dtype=np.float32)
    # for i in ids:
    #     seg_rgb[seg == i] = cmap[i]
    seg = seg.astype(float)  # if we leave it as int, fastremap will truncate the values
    seg_r = fastremap.remap(seg, {k: v[0] for k, v in cmap.items()})
    seg_g = fastremap.remap(seg, {k: v[1] for k, v in cmap.items()})
    seg_b = fastremap.remap(seg, {k: v[2] for k, v in cmap.items()})
    seg_rgb = np.stack([seg_r, seg_g, seg_b], axis=-1)

    return seg_rgb


def apply_global_xforms(points, inverse=False):
    """Apply globally defined transforms to coordinates."""
    global_scale = 1 / get_pref("scale_factor", 10_000)
    up = get_pref("axis_up", "Z")
    forward = get_pref("axis_forward", "Y")

    # Note: `Matrix` is available at global namespace in Blender
    global_matrix = axis_conversion(
        from_forward=forward,
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
    if "cloudblender" in bpy.context.preferences.addons:
        prefs = bpy.context.preferences.addons["cloudblender"].preferences

        if hasattr(prefs, key):
            return getattr(prefs, key)
        elif default:
            return default
        else:
            raise KeyError(f'`cloudblender` has no preference "{key}"')
    else:
        if not isinstance(default, type(None)):
            return default
        else:
            raise KeyError("Could not find `cloudblender` preferences.")


def set_pref(key, value):
    """Set given key in preferences."""
    if "cloudblender" in bpy.context.preferences.addons:
        prefs = bpy.context.preferences.addons["cloudblender"].preferences

        if hasattr(prefs, key):
            setattr(prefs, key, value)
        else:
            raise KeyError(f'`cloudblender` has no preference "{key}"')
    else:
        raise KeyError("Could not find `cloudblender` preferences.")


def clean_node_tree(node_tree):
    """Clear all nodes in a shader node tree except the output.

    Returns the output node
    """
    nodes = node_tree.nodes
    for node in list(nodes):  # copy to avoid altering the loop's data source
        if not node.type == "OUTPUT_MATERIAL":
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
        node_tree = bpy.data.node_groups["IAP_SHADELESS"]

    except KeyError:
        # need to build node shadeless node group
        node_tree = bpy.data.node_groups.new("IAP_SHADELESS", "ShaderNodeTree")
        output_node = node_tree.nodes.new("NodeGroupOutput")
        input_node = node_tree.nodes.new("NodeGroupInput")

        node_tree.outputs.new("NodeSocketShader", "Shader")
        node_tree.inputs.new("NodeSocketColor", "Color")

        # This could be faster as a transparent shader, but then no ambient occlusion
        diffuse_shader = node_tree.nodes.new("ShaderNodeBsdfDiffuse")
        node_tree.links.new(diffuse_shader.inputs[0], input_node.outputs[0])

        emission_shader = node_tree.nodes.new("ShaderNodeEmission")
        node_tree.links.new(emission_shader.inputs[0], input_node.outputs[0])

        light_path = node_tree.nodes.new("ShaderNodeLightPath")
        is_glossy_ray = light_path.outputs["Is Glossy Ray"]
        is_shadow_ray = light_path.outputs["Is Shadow Ray"]
        ray_depth = light_path.outputs["Ray Depth"]
        transmission_depth = light_path.outputs["Transmission Depth"]

        unrefracted_depth = node_tree.nodes.new("ShaderNodeMath")
        unrefracted_depth.operation = "SUBTRACT"
        unrefracted_depth.label = "Bounce Count"
        node_tree.links.new(unrefracted_depth.inputs[0], ray_depth)
        node_tree.links.new(unrefracted_depth.inputs[1], transmission_depth)

        refracted = node_tree.nodes.new("ShaderNodeMath")
        refracted.operation = "SUBTRACT"
        refracted.label = "Camera or Refracted"
        refracted.inputs[0].default_value = 1.0
        node_tree.links.new(refracted.inputs[1], unrefracted_depth.outputs[0])

        reflection_limit = node_tree.nodes.new("ShaderNodeMath")
        reflection_limit.operation = "SUBTRACT"
        reflection_limit.label = "Limit Reflections"
        reflection_limit.inputs[0].default_value = 2.0
        node_tree.links.new(reflection_limit.inputs[1], ray_depth)

        camera_reflected = node_tree.nodes.new("ShaderNodeMath")
        camera_reflected.operation = "MULTIPLY"
        camera_reflected.label = "Camera Ray to Glossy"
        node_tree.links.new(camera_reflected.inputs[0], reflection_limit.outputs[0])
        node_tree.links.new(camera_reflected.inputs[1], is_glossy_ray)

        shadow_or_reflect = node_tree.nodes.new("ShaderNodeMath")
        shadow_or_reflect.operation = "MAXIMUM"
        shadow_or_reflect.label = "Shadow or Reflection?"
        node_tree.links.new(shadow_or_reflect.inputs[0], camera_reflected.outputs[0])
        node_tree.links.new(shadow_or_reflect.inputs[1], is_shadow_ray)

        shadow_or_reflect_or_refract = node_tree.nodes.new("ShaderNodeMath")
        shadow_or_reflect_or_refract.operation = "MAXIMUM"
        shadow_or_reflect_or_refract.label = "Shadow, Reflect or Refract?"
        node_tree.links.new(
            shadow_or_reflect_or_refract.inputs[0], shadow_or_reflect.outputs[0]
        )
        node_tree.links.new(
            shadow_or_reflect_or_refract.inputs[1], refracted.outputs[0]
        )

        mix_shader = node_tree.nodes.new("ShaderNodeMixShader")
        node_tree.links.new(
            mix_shader.inputs[0], shadow_or_reflect_or_refract.outputs[0]
        )
        node_tree.links.new(mix_shader.inputs[1], diffuse_shader.outputs[0])
        node_tree.links.new(mix_shader.inputs[2], emission_shader.outputs[0])

        node_tree.links.new(output_node.inputs[0], mix_shader.outputs[0])

        auto_align_nodes(node_tree)

    group_node = dest_node_tree.nodes.new("ShaderNodeGroup")
    group_node.node_tree = node_tree

    return group_node


def try_int(x):
    """Try to convert x to an integer, returning x if it fails."""
    try:
        return int(x)
    except ValueError:
        return x


def create_cycles_texnode(node_tree, image):
    """Create a Cycles texture node from an image."""
    image_src = bpy.data.images.new("src", image.shape[0], image.shape[1])

    # Normalize integers
    if image.dtype in (np.uint8, np.uint16, np.uint32):
        image = image / np.iinfo(VOLUME_IMG.meta.dtype).max

    # Need to invert the image rows
    image = image[::-1, ::-1]

    # We need to flatten the image into a single channel
    image_channeled = np.ones(len(image_src.pixels), dtype=np.float64)

    # If this is greyscale
    if image.ndim == 2:
        for i in range(3):
            image_channeled[i::4] = image.flatten(order="F")
    # If this is RBB
    elif image.ndim == 3:
        assert image.shape[2] == 3
        for i in range(3):
            image_channeled[i::4] = image[:, :, i].flatten(order="F")
    else:
        raise ValueError("Invalid image shape:", image.shape)
    image_src.pixels[:] = image_channeled
    # image_src.source = 'FILE'
    image_src.update()

    tex_image = node_tree.nodes.new("ShaderNodeTexImage")
    tex_image.image = image_src
    tex_image.extension = "CLIP"
    tex_image.show_texture = True
    return tex_image


def auto_align_nodes(node_tree):
    """Given a shader node tree, arrange nodes neatly relative to the output node."""
    x_gap = 200
    y_gap = 180
    nodes = node_tree.nodes
    links = node_tree.links
    output_node = None
    for node in nodes:
        if node.type == "OUTPUT_MATERIAL" or node.type == "GROUP_OUTPUT":
            output_node = node
            break

    else:  # Just in case there is no output
        return


########################################
#  Preferences
########################################


@orientation_helper(axis_forward="-Z", axis_up="-Y")
class CLOUDBLENDER_preferences(AddonPreferences):
    bl_idname = __name__

    server_img: StringProperty(
        name="Image source",
        default="precomputed://https://bossdb-open-data.s3.amazonaws.com/iarpa_microns/minnie/minnie65/em",
    )
    server_seg: StringProperty(
        name="Segmentation source",
        default="precomputed://gs://iarpa_microns/minnie/minnie65/seg",
    )
    use_cache: BoolProperty(
        name="Use cache",
        default=True,
        description="Use local cache for images and segmentation data.",
    )
    use_https: BoolProperty(name="Use https", default=True)
    max_threads: IntProperty(
        name="Max parallel requests",
        default=1,
        min=1,
        description="Restricting the number of parallel "
        "requests can help if you get errors "
        "when loading loads of neurons.",
    )
    scale_factor: IntProperty(
        name="Conversion factor to Blender units",
        default=10_000,
        description="Volume units will be divided "
        "by this factor when imported "
        "into Blender.",
    )

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.prop(self, "server_img")
        box.prop(self, "server_seg")
        box.prop(self, "use_https")
        box.prop(self, "use_cache")

        box = layout.box()
        box.label(text="Connection settings:")
        box.prop(self, "max_threads")

        box = layout.box()
        box.label(text="Import options:")
        box.prop(self, "scale_factor")
        box.prop(self, "axis_forward")
        box.prop(self, "axis_up")


########################################
#  Registration stuff
########################################


classes = (
    CLOUDBLENDER_PT_import_panel,
    CLOUDBLENDER_OP_connect,
    CLOUDBLENDER_OP_show_bounds,
    CLOUDBLENDER_OP_fetch_slices,
    CLOUDBLENDER_OP_fetch_cube,
    CLOUDBLENDER_OP_update_images,
    CLOUDBLENDER_OP_fetch_mesh,
    CLOUDBLENDER_OP_color_neurons,
    CLOUDBLENDER_preferences,
    CLOUDBLENDER_OP_install,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in classes[::-1]:
        bpy.utils.unregister_class(c)


# This allows us to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()
