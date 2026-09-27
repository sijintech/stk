#ifndef INP_IO_H
#define INP_IO_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#define MAX_LINE_LENGTH 256      // Abaqus 规定每行最大256字符
#define MAX_KEYWORD_LENGTH 80    // 关键字最大长度
#define MAX_PARAM_NAME_LENGTH 80 // 参数名最大长度
#define MAX_PARAM_VALUE_LENGTH 256 // 参数值最大长度
#define MAX_KEYWORDS 1000        // 最大关键字数量
#define MAX_PARAMS_PER_KEYWORD 50 // 每个关键字最大参数数量
#define MAX_DATA_LINES_PER_KEYWORD 1000 // 每个关键字最大数据行数量

// 参数结构体
typedef struct {
    char name[MAX_PARAM_NAME_LENGTH];     // 参数名
    char value[MAX_PARAM_VALUE_LENGTH];   // 参数值
    int has_value;                        // 是否有值（标志参数 vs 赋值参数）
} inp_parameter_t;

// 数据行结构体
typedef struct {
    char content[MAX_LINE_LENGTH];        // 原始数据行内容
    char** fields;                        // 解析后的字段数组
    int field_count;                      // 字段数量
} inp_data_line_t;

// 关键字块结构体
typedef struct {
    char name[MAX_KEYWORD_LENGTH];        // 关键字名称（不含*）
    inp_parameter_t parameters[MAX_PARAMS_PER_KEYWORD]; // 参数数组
    int parameter_count;                  // 参数数量
    inp_data_line_t* data_lines;         // 数据行数组
    int data_line_count;                  // 数据行数量
    int line_number;                      // 在文件中的行号
} inp_keyword_t;

// 文件元信息结构体
typedef struct {
    char filename[256];                   // 文件名
    int total_lines;                      // 总行数
    int keyword_count;                    // 关键字数量
    int comment_lines;                    // 注释行数量
    char parse_errors[1024];              // 解析错误信息
} inp_metadata_t;

// 主要的输入文件结构体
typedef struct {
    inp_keyword_t* keywords;              // 关键字数组
    int keyword_count;                    // 关键字数量
    inp_metadata_t metadata;              // 文件元信息
} inp_file_t;

// 解析结果枚举
typedef enum {
    INP_SUCCESS = 0,
    INP_ERROR_FILE_NOT_FOUND = -1,
    INP_ERROR_MEMORY_ALLOCATION = -2,
    INP_ERROR_INVALID_FORMAT = -3,
    INP_ERROR_LINE_TOO_LONG = -4,
    INP_ERROR_INVALID_KEYWORD = -5
} inp_result_t;

// 主要解析函数
inp_result_t inp_parse_file(const char* filepath, inp_file_t** result);

// 内存管理函数
void inp_free_file(inp_file_t* file);

// 工具函数
const inp_keyword_t* inp_find_keyword(const inp_file_t* file, const char* keyword_name);
void inp_print_file_info(const inp_file_t* file);

#endif // INP_IO_H
