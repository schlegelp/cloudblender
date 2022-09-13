# cloudblender [WIP]
Blender wrapper for [`cloud-volume`](https://github.com/seung-lab/cloud-volume)

The basic idea is to let you import image data, skeletons and meshes from
any data source that `cloud-volume` understands.

- [x] import image data as planes/cubes
- [ ] import segmentation data as planes/cubes
- [ ] import meshes
- [ ] import skeletons


## Installation

First you need to install `cloud-volume` for Blender's Python: open Blender
and in "scripting" use below code to find the executable for Python

```Python
>>> import sys
>>> sys.executable
'/Applications/Blender.app/Contents/Resources/3.0/python/bin/python3.9'
```

Next, open a terminal and run this:

```bash
$ /Applications/Blender.app/Contents/Resources/3.0/python/bin/python3.9 -m pip install cloud-volume
```

In an ideal world the install will just work but that's hardly ever the case.
Some issues I encountered:

- `pip` not installed: this is actually easy enough to fix (just Google it).
- `cloud-volume` dependencies need to be compiled from source and that fails:
  this is a pain in the a** in particular because Blender ships Python without
  the header files. I had the most success by building wheels for the missing
  dependencies on my system's Python (must be same version) and then use those
  wheels with Blender's Python.  

Finally: download `cloudblender.py`, fire up Blender, go to "Edit" -> "Preferences"
-> "Add-ons" -> "Install" and select the file. Make sure to activate the
add-on.
