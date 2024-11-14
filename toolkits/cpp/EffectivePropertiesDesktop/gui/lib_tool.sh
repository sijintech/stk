#!/bin/sh

# show execute the following command in the gui folder
# For different software, you need to change the following variables
SOFTNAME="MUPRO-Effective-Properties"
FOLDER="/Users/xiaoxingcheng/Code/suan-pc-effprop"
EXECUTABLE_PATH="Contents/effprop"

# Below you shouldn't need to change anything
PWD=(`pwd`)
BUILT_PRODUCTS_DIR=(`echo $PWD/dist/mac/$SOFTNAME.app`)
FRAMEWORKS_FOLDER_PATH="Contents/Frameworks"
version=$1

app=$BUILT_PRODUCTS_DIR/$EXECUTABLE_PATH
fw_path=$BUILT_PRODUCTS_DIR/$FRAMEWORKS_FOLDER_PATH

function change_paths {
    local index=$1
    let index1=$index+1 
    local bin=$2
    local old=$3
    binbase=$(basename $bin)
    echo change_path $bin
    dyl_list=(`otool -L $bin | grep local | awk '{print $1}'`)
    if [ ! -z "$dyl_list" ]; then
        for dyl in ${dyl_list[*]}; do
            libname=$(basename $dyl)
            printf "Local %i %s" $index $libname
            if [ "$libname" != "$binbase" ]; then
                # sudo cp $dyl $fw_path/
                printf "copy %i \t%s\n" $index $dyl
                install_name_tool -change $dyl "@executable_path/Frameworks/$libname" $bin
                printf "change %i \t%s of %s\n" $index $dyl $bin
                change_paths $index1 $fw_path/$libname $dyl
            else
                install_name_tool -id "@executable_path/Frameworks/$libname" $fw_path/$libname
                printf "id %i \t%s\n" $index $dyl
            fi
        done
    fi

    dyl_list=(`otool -L $bin | grep loader_path | awk '{print $1}'`)
    if [ ! -z "$dyl_list" ]; then
        if [ ! -z "$old" ]; then
            dir=(`dirname $old`)
            for dyl in ${dyl_list[*]}; do
                libname=$(basename $dyl)
                printf "loader_path %i %s" $index $libname
                relp=(`echo $dyl | awk 'BEGIN{FS="/"};{for (i=2; i<=NF-1; i++) printf $i"/";print $NF}'`)
                dirn=(`echo $dir/$relp`);
                if [ "$libname" != "$binbase" ]; then
                    # sudo cp $dirn $fw_path/
                    printf "copy %i \t%s\n" $index $dirn
                    install_name_tool -change $dyl "@loader_path/$libname" $bin
                    printf "change %i \t%s of %s\n" $index $dyl $bin
                    change_paths $index1 $fw_path/$libname $dirn
                else
                    install_name_tool -id "@executable_path/Frameworks/$libname" $fw_path/$libname
                    printf "id %i \t%s\n" $index $dyl
                fi
            done
        else
            printf "the old director is not given, %i %s" $index $bin
        fi
    fi
}

# cp /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX11.3.sdk/usr/lib/libxml2.2.tbd ${fw_path}
# cp /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX11.3.sdk/usr/lib/libcurl.4.tbd ${fw_path}
# cp /usr/local/Cellar/fftw/3.3.9/lib/libfftw3.3.dylib  ${fw_path}
# 1. use the above to define the function, then run for the main app
change_paths 0 $app

# 2. next run for all the lib within framework
app_dyl_list=(`ls $fw_path | grep dylib`)
for dyl_bin in ${app_dyl_list[*]}; do
    change_paths 0 $fw_path/$dyl_bin
done

codesign --sign 947ED3D858E6E46A2C4E47945E82AC63079D4074 --force --timestamp --options runtime --deep --entitlements $FOLDER/gui/node_modules/app-builder-lib/templates/entitlements.mac.plist $FOLDER/gui/dist/mac/$SOFTNAME.app

# 3. create the dmg
create-dmg \
    --volname "$SOFTNAME-$version" \
    --window-pos 200 120 \
    --window-size 800 400 \
    --icon-size 100 \
    --icon "$SOFTNAME.app" 200 190 \
    --hide-extension "$SOFTNAME.app" \
    --app-drop-link 600 185 \
    "dist/$SOFTNAME-$version.dmg" \
    "dist/mac/"