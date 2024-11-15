function batchAllCommand() {
  # This command will loop through all folders and execute a command
  # input: 1. the command you want to execute
  # 2. is an optional directory wild card, default to ./*

  local command_string="$1"
  local folder_string="./*"
  if [ ! -z "$2" ]; then
    local folder_string="$2"
  fi
  local folder_array=($(find $folder_string -type d))
  local current_dir=$(eval pwd)
  local dir=""

  for dir in $folder_array; do
    if [[ -d ${dir} ]]; then
      cd ${dir}
      echo "-- Executing ${command_string} in ${dir}"
      eval "${command_string}"
      cd ${current_dir}
    fi
  done


  #sleep 0.1
}
