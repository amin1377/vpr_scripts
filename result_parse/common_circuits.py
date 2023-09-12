import os

def get_subdirs(directory):
    return [name for name in os.listdir(directory) if os.path.isdir(os.path.join(directory, name))]

# Replace these with the actual paths to the directories
dir1 = '/home/amin/wintermute_mount/run_koios/run003/aman_3d_limited.xml'
dir2 = '/home/amin/wintermute_mount/run_koios/run001/aman_3d_coffe.xml'

# Get the subdirectories in each directory
subdirs1 = set(get_subdirs(dir1))
subdirs2 = set(get_subdirs(dir2))

# Find the subdirectories that are not common between the two directories
unique_subdirs = subdirs1.symmetric_difference(subdirs2)

print("Subdirectories unique to dir1:")
for subdir in unique_subdirs:
    if subdir in subdirs1:
        print(subdir)

print("\nSubdirectories unique to dir2:")
for subdir in unique_subdirs:
    if subdir in subdirs2:
        print(subdir)
