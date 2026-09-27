---
head:
  - - link
    - rel: stylesheet
      href: https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.5.1/katex.min.css
---

# Thermal conductivity of three phase structure

For details about the effective thermal conductivity calculation, please see [here](/manual/thermal).

## Overview

First, we will setup a cubic simulation with 128 microns along each dimension, that is 128 simulation grids times 1 micrometer for each grid.

Next, we will add three phases into the system, one for the matrix phase, another for the slab with higher conductivity, and the other for the embedded particle with lower conductivity.

Lastly, we will setup a structure with slab and random ellipsoid for the composite material.

## Step 1: Fill Input

<!--@include: ./step_1.md-->

### Dimension

> ![dimension](image/dimension_128_1e-6.jpg){ width=60%,height:30px }

### Output

<!--@include: ./output.md-->

### System

Choose "Thermal" system for the **System Type**.
Besides from the effective properties of thermal conductivity, we also want to calculate a field distribution under external applied thermal gradient, so we need to turn on the **Distribution** switch and set an **Tenp. grad (k/m)** value, the temperature gradient in kelvin per meter.

Next, set the reference thermal conductivity value to be used in our solver.

> ![system](image/thermal_system.jpg){width=60%,height:30px}

Then, set the thermal conductivity for the three phases.

> ![phase0](image/thermal_phase0.jpg){width=60%,height:30px}

> ![phase1](image/thermal_phase1.jpg){width=60%,height:30px}

> ![phase2](image/thermal_phase2.jpg){width=60%,height:30px}

### Structure

Since we want to generate the structure within the effective properties simulation program, we should choose "Generate from xml file" for the **Source type**.

Click **Add Geometry** button to create a new geometry tab, and set label 0 as the **Default label**.

We want to create 10 randomly generated ellipsoids whose centers are located in the lower half of the 128 cube, and leave the upper half for the slab.

The ellipsoid radius is random value between 4 to 16 grid points, and there is no rotation added to the ellipsoid.

We will assign phase label 1 to this newly defined geometry and set its matrix label to be phase 0.

> ![structure](image/thermal_geometry0.jpg){width=60%,height:30px}

To set the slab structure, we click the **Add Geometry** again and choose Slab for **Geometry type**

> ![structure](image/thermal_geometry1.jpg){width=60%,height:30px}

## Step 1.5: Or Import Input

<!--@include: ./step_1.5.md-->

```xml
<input>
  <dimension>
    <nx>128</nx>
    <ny>128</ny>
    <nz>128</nz>
    <dx>1e-6</dx>
    <dy>1e-6</dy>
    <dz>1e-6</dz>
  </dimension>
  <output>
    <format>vti</format>
  </output>
  <system>
    <type>thermal</type>
    <distribution>1</distribution>
    <external>
      <temperatureGradient>
        <x>0</x>
        <y>0</y>
        <z>100</z>
      </temperatureGradient>
    </external>
    <solver>
      <ref>
        <tensor>
          <name>thermal_conductivity</name>
          <rank>2</rank>
          <pointGroup>custom</pointGroup>
          <component>
            <value>100</value>
            <index>11</index>
            <index>22</index>
            <index>33</index>
          </component>
        </tensor>
      </ref>
    </solver>
    <material>
      <phase>
        <label>0</label>
        <tensor>
          <name>thermal_conductivity</name>
          <rank>2</rank>
          <pointGroup>custom</pointGroup>
          <component>
            <value>10</value>
            <index>11</index>
            <index>22</index>
            <index>33</index>
          </component>
        </tensor>
      </phase>
      <phase>
        <label>1</label>
        <tensor>
          <name>thermal_conductivity</name>
          <rank>2</rank>
          <pointGroup>custom</pointGroup>
          <component>
            <value>100</value>
            <index>11</index>
            <index>22</index>
            <index>33</index>
          </component>
        </tensor>
      </phase>
      <phase>
        <label>2</label>
        <tensor>
          <name>thermal_conductivity</name>
          <rank>2</rank>
          <pointGroup>custom</pointGroup>
          <component>
            <value>1</value>
            <index>11</index>
            <index>22</index>
            <index>33</index>
          </component>
        </tensor>
      </phase>
    </material>
  </system>
  <structure>
    <matrixLabel>0</matrixLabel>
    <sourceType>xml</sourceType>
    <geometry>
      <type>ellipsoid_random</type>
      <count>10</count>
      <centerXMin>32</centerXMin>
      <centerXMax>96</centerXMax>
      <centerYMin>32</centerYMin>
      <centerYMax>96</centerYMax>
      <centerZMin>16</centerZMin>
      <centerZMax>48</centerZMax>
      <radiusXMin>4</radiusXMin>
      <radiusXMax>16</radiusXMax>
      <radiusYMin>4</radiusYMin>
      <radiusYMax>16</radiusYMax>
      <radiusZMin>4</radiusZMin>
      <radiusZMax>16</radiusZMax>
      <rotationXMin>0</rotationXMin>
      <rotationXMax>0</rotationXMax>
      <rotationYMin>0</rotationYMin>
      <rotationYMax>0</rotationYMax>
      <rotationZMin>0</rotationZMin>
      <rotationZMax>0</rotationZMax>
      <label>1</label>
      <matrixLabel>0</matrixLabel>
    </geometry>
    <geometry>
      <type>slab</type>
      <centerX>0</centerX>
      <centerY>0</centerY>
      <centerZ>72</centerZ>
      <normalX>0</normalX>
      <normalY>0</normalY>
      <normalZ>1</normalZ>
      <thickness>10</thickness>
      <label>2</label>
      <matrixLabel>0</matrixLabel>
    </geometry>
  </structure>
</input>
```

## Step 2: Export Input

<!--@include: ./step_2.md-->

## Step 3: Run calculation

<!--@include: ./step_3.md-->

## Step 4: Check Output

You will see the following output files in your simulation folder. Meaning for each of the files are explained in the [Dielectric System](/manual/dielectric#output-files).

> ![structure](image/thermal_output_files.jpg){width=80%,height:30px}

Overall, there are two types of output data, vti files for 3D data, and csv files for tabular data.

## Step 4.1: Check 3D data

Within our software, you can quickly check a 3D vti data file.

Select the file you want to visualize using the dropdown menu, then click **Load data** button.

> ![select_data](image/thermal_output_select.jpg){width=60%}

Then you will see something like this.

> ![microstructure](image/thermal_microstructure.jpg){width=100%}

## Step 4.2: Paraview

Next, we can try visualizing other files with Paraview. Click the first **Open** icon in the tool bar.

> ![paraview_open](image/thermal_paraview.jpg){width=100%}

After the data is loaded, click **Apply**, then switch to **Volume** rendering and choose **scalar_data_2**, which is electric field along z for visualization.

We also need to tune the color lookup table to add some transparency to the data.

> ![paraview_view](image/thermal_paraview_temperature.jpg){width=100%}

## Step 4.3: Check tabular data

Though 3D data looks cool, the more important thing probably is still the effective permittivity, _out_effective_permittivity.csv_.

| Index | 1             | 2             | 3             |
| ----- | ------------- | ------------- | ------------- |
| 1     | +9.580886e+00 | +1.757357e-03 | -4.381574e-03 |
| 2     | +1.757357e-03 | +9.566548e+00 | +1.616383e-03 |
| 3     | -9.079212e-03 | +3.559258e-03 | +6.093892e+00 |
