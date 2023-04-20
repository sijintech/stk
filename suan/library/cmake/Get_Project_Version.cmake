macro(Get_Project_Version PROJECT_NAME HEADER_FILE)

file(STRINGS "${HEADER_FILE}" HEADER_FILE_CONTENT 
    REGEX "^#define ${PROJECT_NAME}_VERSION_(MAJOR|MINOR|BUILD) +[0-9]+$"
)

set(PROJECT_VERSION_MAJOR 0)
set(PROJECT_VERSION_MINOR 0)
set(PROJECT_VERSION_PATCH 0)

foreach(VERSION_LINE IN LISTS HEADER_FILE_CONTENT)
    foreach(VERSION_PART MAJOR MINOR PATCH)
        string(CONCAT REGEX_STRING "#define "
                                   "${PROJECT_NAME}"
                                   "_VERSION_" 
                                   "${VERSION_PART}" 
                                   " +([0-9]+)"
        )

        if(VERSION_LINE MATCHES "${REGEX_STRING}")
            set(PROJECT_VERSION_${VERSION_PART} "${CMAKE_MATCH_1}")
        endif()
    endforeach()
endforeach()
endmacro()
