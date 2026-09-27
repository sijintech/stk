/**
 * C 语言使用示例
 * 
 * 此示例展示了如何在 C 程序中使用 inp_io 库解析 Abaqus 输入文件
 * 并访问解析后的数据结构。
 * 
 * 编译方法:
 * gcc -o c_example c_example.c -I.. -L.. -linp_io
 */

#include "../inp_io.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char* argv[]) {
    const char* filepath = "example.inp";
    
    // 使用命令行传入的文件名（如果有）
    if (argc > 1) {
        filepath = argv[1];
    }
    
    printf("=== inp_io C 语言使用示例 ===\n");
    printf("解析文件: %s\n\n", filepath);
    
    // 变量定义
    inp_file_t* inp_file = NULL;
    inp_result_t result;
    
    // 解析文件
    result = inp_parse_file(filepath, &inp_file);
    if (result != INP_SUCCESS) {
        printf("解析失败，错误码: %d\n", result);
        return 1;
    }
    
    // 打印基本文件信息
    printf("文件已成功解析!\n");
    printf("关键字总数: %d\n", inp_file->keyword_count);
    printf("文件总行数: %d\n", inp_file->metadata.total_lines);
    printf("注释行数量: %d\n\n", inp_file->metadata.comment_lines);
    
    // 查找并显示材料信息
    const inp_keyword_t* material = inp_find_keyword(inp_file, "MATERIAL");
    if (material) {
        int material_count = 0;
        
        // 统计材料数量
        for (int i = 0; i < inp_file->keyword_count; i++) {
            if (strcasecmp(inp_file->keywords[i].name, "MATERIAL") == 0) {
                material_count++;
            }
        }
        
        printf("找到 %d 个材料定义:\n", material_count);
        
        // 遍历所有材料
        for (int i = 0; i < inp_file->keyword_count; i++) {
            if (strcasecmp(inp_file->keywords[i].name, "MATERIAL") == 0) {
                const inp_keyword_t* mat = &inp_file->keywords[i];
                
                // 查找材料名称
                const char* mat_name = "未命名";
                for (int j = 0; j < mat->parameter_count; j++) {
                    if (strcasecmp(mat->parameters[j].name, "NAME") == 0 && 
                        mat->parameters[j].has_value) {
                        mat_name = mat->parameters[j].value;
                        break;
                    }
                }
                
                printf("  材料 #%d: %s\n", i+1, mat_name);
                
                // 查找材料的弹性属性（通常跟在MATERIAL关键字后）
                if (i+1 < inp_file->keyword_count && 
                    strcasecmp(inp_file->keywords[i+1].name, "ELASTIC") == 0) {
                    
                    const inp_keyword_t* elastic = &inp_file->keywords[i+1];
                    
                    // 通常弹性属性的第一个数据行包含杨氏模量和泊松比
                    if (elastic->data_line_count > 0 && 
                        elastic->data_lines[0].field_count >= 2) {
                        
                        printf("    杨氏模量: %s\n", elastic->data_lines[0].fields[0]);
                        printf("    泊松比: %s\n", elastic->data_lines[0].fields[1]);
                    }
                }
            }
        }
    } else {
        printf("未找到材料定义\n");
    }
    
    printf("\n");
    
    // 查找节点信息
    const inp_keyword_t* node = inp_find_keyword(inp_file, "NODE");
    if (node) {
        printf("找到节点定义，共 %d 个节点\n", node->data_line_count);
        
        // 显示前5个节点（如果有）
        printf("前 %d 个节点坐标:\n", 
               node->data_line_count > 5 ? 5 : node->data_line_count);
        
        for (int i = 0; i < node->data_line_count && i < 5; i++) {
            const inp_data_line_t* node_data = &node->data_lines[i];
            
            if (node_data->field_count >= 4) {
                printf("  节点 #%s: (%s, %s, %s)\n", 
                    node_data->fields[0], 
                    node_data->fields[1],
                    node_data->fields[2],
                    node_data->fields[3]);
            }
        }
    } else {
        printf("未找到节点定义\n");
    }
    
    // 释放内存
    inp_free_file(inp_file);
    printf("\n库函数已正确释放内存\n");
    
    return 0;
}
