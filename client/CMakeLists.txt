cmake_minimum_required(VERSION 3.21)

project(EscapeBotClient VERSION 0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 REQUIRED COMPONENTS Quick Multimedia WebSockets)

qt_standard_project_setup()

qt_add_executable(EscapeBotClient
    src/main.cpp
    src/BackendBridge.cpp
    src/BackendBridge.h
    src/CameraQrBridge.cpp
    src/CameraQrBridge.h
)

qt_add_qml_module(EscapeBotClient
    URI EscapeBot
    VERSION 1.0
    QML_FILES
        qml/Main.qml
    RESOURCES
        shaders/crt.frag
        shaders/glitch.frag
)

target_link_libraries(EscapeBotClient
    PRIVATE
        Qt6::Quick
        Qt6::Multimedia
        Qt6::WebSockets
)
