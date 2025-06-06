# Compiler and flags
CXX = g++-13
CXXFLAGS = -std=c++20 -Wall -Wextra -O3 -DPUGIXML_COMPACT
LDFLAGS = -lpthread

# Source and target
SOURCES = $(wildcard *.cpp)
OBJECTS = $(SOURCES:.cpp=.o)
TARGET = my_program

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CXX) $(OBJECTS) -o $@ $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS) $(TARGET)