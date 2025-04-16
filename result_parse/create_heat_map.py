import numpy as np
import matplotlib.pyplot as plt

# Load data from CSV
data = np.loadtxt("mux_avg_new.csv", delimiter=',')

# Flip vertically so that y=0 is at the bottom
data = np.flipud(data)

# Set extent: [x_min, x_max, y_min, y_max]
num_x = data.shape[1]
num_y = data.shape[0]

plt.imshow(
    data,
    cmap='hot',
    origin='lower',
    extent=[0, num_x, 0, num_y],  # ensures each bin is 1x1 in size
    aspect='auto'  # keeps scaling correct even if not square
)

plt.colorbar(label='Average MUX Size')
plt.title("Grid MUX Size Heatmap New")
plt.xlabel("X")
plt.ylabel("Y")

plt.grid(False)
plt.show()