#include "niobasic/path.h"

void n_path_get_cwd(char *out)
{
#ifdef WIN32
    TCHAR path[MAX_PATH] = {0};
    GetCurrentDirectory(MAX_PATH, path);
#else
    char path[MAX_PATH]={0};
    getcwd(path, MAX_PATH);
#endif
    strcpy(out, path);
}

void n_path_get_exe_path(char *out)
{
#ifdef WIN32
    TCHAR path[MAX_PATH] = {0};
    GetModuleFileName(NULL, path, MAX_PATH);
#elif __APPLE__
    char path[MAX_PATH] = {0};
    uint32_t size=sizeof(path);
    _NSGetExecutablePath(path,&size);
#else
    char path[MAX_PATH] = {0};
    readlink("/proc/self/exe", path, MAX_PATH);
#endif
    strcpy(out, path);
}

void n_path_get_exe_folder(char *out)
{
    // TODO: This is only for windows, need to add support for unix system
    n_path_get_exe_path(out);
#ifdef WIN32
    PathRemoveFileSpec(out);
#else
    char *tmp = strdup(out);
    char *path;
    path = dirname(tmp);
    strcpy(out,path);
#endif
    // ZF_LOGI("Current working dir: %s\n", out);
}

void combine(char* destination, const char* path1, const char* path2)
{
    if(path1 == NULL && path2 == NULL) {
        strcpy(destination, "");;
    }
    else if(path2 == NULL || strlen(path2) == 0) {
        strcpy(destination, path1);
    }
    else if(path1 == NULL || strlen(path1) == 0) {
        strcpy(destination, path2);
    } 
    else {
        char directory_separator[] = "/";
#ifdef WIN32
        directory_separator[0] = '\\';
#endif
        const char *last_char = path1;
        while(*last_char != '\0')
            last_char++;        
        int append_directory_separator = 0;
        if(strcmp(last_char, directory_separator) != 0) {
            append_directory_separator = 1;
        }
        strcpy(destination, path1);
        if(append_directory_separator)
            strcat(destination, directory_separator);
        strcat(destination, path2);
    }
}

void n_path_concat(char *path, char *extension)
{
#ifdef WIN32
    TCHAR temp[MAX_PATH] = {0};
    strcpy(temp, path);
    PathCombine(path, temp, extension);
#else
    char temp[MAX_PATH] = {0};
    strcpy(temp, path);
    combine(path,temp,extension);
#endif
}

void n_path_combine(char *out, char *path, char *extension)
{
#ifdef WIN32
    PathCombine(out, path, extension);
#else
    combine(out,path,extension);
#endif
}