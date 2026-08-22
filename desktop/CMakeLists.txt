cmake_minimum_required(VERSION 3.21)

project(EscapeBotDesktop VERSION 0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Core Network Widgets WebEngineWidgets)

qt_add_executable(EscapeBotDesktop
    src/main.cpp
    src/MainWindow.cpp
    src/MainWindow.h
    src/HotspotController.cpp
    src/HotspotController.h
    src/BackendController.cpp
    src/BackendController.h
    src/LocalAdminPage.cpp
    src/LocalAdminPage.h
)

qt_add_executable(EscapeBotCloudOperator
    src/cloud_main.cpp
    src/CloudOperatorWindow.cpp
    src/CloudOperatorWindow.h
    src/CloudLifecycleController.cpp
    src/CloudLifecycleController.h
    src/CloudAdminPage.cpp
    src/CloudAdminPage.h
)

target_link_libraries(EscapeBotDesktop
    PRIVATE
        Qt6::Core
        Qt6::Network
        Qt6::Widgets
        Qt6::WebEngineWidgets
)

target_link_libraries(EscapeBotCloudOperator
    PRIVATE
        Qt6::Core
        Qt6::Network
        Qt6::Widgets
        Qt6::WebEngineWidgets
)

install(TARGETS EscapeBotDesktop EscapeBotCloudOperator
    BUNDLE DESTINATION .
    RUNTIME DESTINATION bin
)
