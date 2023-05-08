# add_subdirectory(License)

install(
  DIRECTORY Visualization
  DESTINATION ./tools
  COMPONENT ${PROJECT_NAME})

install(
  DIRECTORY DataManagement
  DESTINATION ./tools
  COMPONENT ${PROJECT_NAME})

install(
  DIRECTORY StructureGenerator
  DESTINATION ./tools
  COMPONENT ${PROJECT_NAME})
