import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

# 1. Canvas setup with a clean blueprint-style grid
fig, ax = plt.subplots(figsize=(11, 9))
ax.set_aspect('equal')
plt.grid(True, linestyle='--', color='#e0e0e0', alpha=0.7)

# --- FOUNDATION COMPONENTS ---

# Outer Footing Outline (10m x 8m) - Light grey fill, dashed edge
outer_footing = Rectangle((0, 0), 10, 8, facecolor='#f2f2f2', edgecolor='#7f8c8d', linewidth=1.5, linestyle='--')
# Inner Footing Cutout (Leaves a 0.6m wide concrete footprint all around)
inner_footing_cutout = Rectangle((0.6, 0.6), 8.8, 6.8, facecolor='white', edgecolor='#7f8c8d', linewidth=1.5, linestyle='--')

# Concrete Stem Walls (0.3m wide, centered perfectly on the 0.6m footing)
# Placed at X=0.15, Y=0.15 to stay perfectly aligned
outer_wall = Rectangle((0.15, 0.15), 9.7, 7.7, facecolor='none', edgecolor='#2c3e50', linewidth=3)
inner_wall_cutout = Rectangle((0.45, 0.45), 9.1, 7.1, facecolor='none', edgecolor='#2c3e50', linewidth=3)

# Add elements to canvas in proper layered order
ax.add_patch(outer_footing)
ax.add_patch(inner_footing_cutout)
ax.add_patch(outer_wall)
ax.add_patch(inner_wall_cutout)

# Internal Support Piers/Columns (Isolated Concrete Pads)
pier1 = Rectangle((3.0, 3.7), 0.6, 0.6, facecolor='#bdc3c7', edgecolor='black', linewidth=1.5)
pier2 = Rectangle((6.4, 3.7), 0.6, 0.6, facecolor='#bdc3c7', edgecolor='black', linewidth=1.5)
ax.add_patch(pier1)
ax.add_patch(pier2)


# --- ARCHITECTURAL DIMENSION LINES ---

def draw_dimension(ax, start, end, text, offset, orientation='horizontal'):
    """Helper tool to draw clean dimension lines outside the structure."""
    x1, y1 = start
    x2, y2 = end
    
    if orientation == 'horizontal':
        # Main line running parallel to the foundation
        ax.plot([x1, x2], [y1 + offset, y2 + offset], color='black', linewidth=1, marker='|', markersize=10)
        # Text block centered right over the dimension line
        ax.text((x1 + x2)/2, y1 + offset + 0.15, text, ha='center', va='bottom', fontsize=10, fontweight='bold')
    else:
        # Vertical dimension layout
        ax.plot([x1 + offset, x2 + offset], [y1, y2], color='black', linewidth=1, marker='_', markersize=10)
        # Rotated text block running parallel to vertical axis
        ax.text(x1 + offset + 0.15, (y1 + y2)/2, text, ha='left', va='center', rotation=270, fontsize=10, fontweight='bold')

# Outer Dimensions (Offset outside the main building borders)
draw_dimension(ax, (0, 0), (10, 0), "10.00 m", offset=-0.8, orientation='horizontal')
draw_dimension(ax, (10, 0), (10, 8), "8.00 m", offset=0.8, orientation='vertical')

# Component Details (Showing footing and wall specific thickness)
draw_dimension(ax, (0, 0), (0.6, 0), "0.60m Footing", offset=-1.5, orientation='horizontal')
draw_dimension(ax, (0.15, 0), (0.45, 0), "0.30m Wall", offset=-2.2, orientation='horizontal')


# --- LABELS AND ANNOTATIONS ---
ax.text(5, 4, "FOUNDATION PLAN\nScale 1:100", ha='center', va='center', fontsize=12, fontweight='bold', color='#2c3e50')
ax.text(3.3, 4.5, "Pier A", fontsize=9, ha='center')
ax.text(6.7, 4.5, "Pier B", fontsize=9, ha='center')

# Canvas View Limits
ax.set_xlim(-2, 12)
ax.set_ylim(-3, 10)
plt.title("Structural Foundation Detail Layout", fontsize=14, pad=20, fontweight='bold')
plt.xlabel("Meters")
plt.ylabel("Meters")

plt.show()
