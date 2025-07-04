#include "inp_io.h"

#ifdef _WIN32
#define strcasecmp _stricmp
#endif


static char* trim_whitespace(char* str) {
    char* end;
    
    
    while(isspace((unsigned char)*str)) str++;
    
    if(*str == 0) return str; 
    
    
    end = str + strlen(str) - 1;
    while(end > str && isspace((unsigned char)*end)) end--;
    
    end[1] = '\0';
    
    return str;
}


static int is_comment_line(const char* line) {
    return (strlen(line) >= 2 && line[0] == '*' && line[1] == '*');
}


static int is_keyword_line(const char* line) {
    return (strlen(line) >= 1 && line[0] == '*' && !(strlen(line) >= 2 && line[1] == '*'));
}


static int is_continuation_line(const char* line) {
    size_t len = strlen(line);
    return (len > 0 && line[len-1] == ',');
}


static inp_result_t parse_keyword_line(const char* line, inp_keyword_t* keyword) {
    if (!line || !keyword) return INP_ERROR_INVALID_FORMAT;
    
    
    char work_line[MAX_LINE_LENGTH];
    strncpy(work_line, line, MAX_LINE_LENGTH - 1);
    work_line[MAX_LINE_LENGTH - 1] = '\0';
    
    
    char* ptr = trim_whitespace(work_line);
    if (*ptr != '*') return INP_ERROR_INVALID_KEYWORD;
    ptr++; 
    
    
    memset(keyword, 0, sizeof(inp_keyword_t));
    keyword->parameter_count = 0;
    keyword->data_line_count = 0;
    keyword->data_lines = NULL;
    
    
    char* comma_pos = strchr(ptr, ',');
    if (comma_pos == NULL) {
        
        strncpy(keyword->name, trim_whitespace(ptr), MAX_KEYWORD_LENGTH - 1);
        keyword->name[MAX_KEYWORD_LENGTH - 1] = '\0';
        return INP_SUCCESS;
    }
    
    
    *comma_pos = '\0';
    strncpy(keyword->name, trim_whitespace(ptr), MAX_KEYWORD_LENGTH - 1);
    keyword->name[MAX_KEYWORD_LENGTH - 1] = '\0';
    
    
    ptr = comma_pos + 1;
    int param_count = 0;
    
    while (*ptr && param_count < MAX_PARAMS_PER_KEYWORD) {
        
        char* next_comma = strchr(ptr, ',');
        char* param_end = next_comma ? next_comma : ptr + strlen(ptr);
        
        
        char param_str[MAX_LINE_LENGTH];
        size_t param_len = param_end - ptr;
        if (param_len >= MAX_LINE_LENGTH) param_len = MAX_LINE_LENGTH - 1;
        strncpy(param_str, ptr, param_len);
        param_str[param_len] = '\0';
        
        
        char* equal_sign = strchr(param_str, '=');
        if (equal_sign) {
            
            *equal_sign = '\0';
            strncpy(keyword->parameters[param_count].name, 
                   trim_whitespace(param_str), MAX_PARAM_NAME_LENGTH - 1);
            keyword->parameters[param_count].name[MAX_PARAM_NAME_LENGTH - 1] = '\0';
            
            strncpy(keyword->parameters[param_count].value, 
                   trim_whitespace(equal_sign + 1), MAX_PARAM_VALUE_LENGTH - 1);
            keyword->parameters[param_count].value[MAX_PARAM_VALUE_LENGTH - 1] = '\0';
            keyword->parameters[param_count].has_value = 1;
        } else {
            
            strncpy(keyword->parameters[param_count].name, 
                   trim_whitespace(param_str), MAX_PARAM_NAME_LENGTH - 1);
            keyword->parameters[param_count].name[MAX_PARAM_NAME_LENGTH - 1] = '\0';
            keyword->parameters[param_count].value[0] = '\0';
            keyword->parameters[param_count].has_value = 0;
        }
        
        param_count++;
        
        if (!next_comma) break;
        ptr = next_comma + 1;
    }
    
    keyword->parameter_count = param_count;
    return INP_SUCCESS;
}


static inp_result_t parse_data_line(const char* line, inp_data_line_t* data_line) {
    if (!line || !data_line) return INP_ERROR_INVALID_FORMAT;
    
    
    strncpy(data_line->content, line, MAX_LINE_LENGTH - 1);
    data_line->content[MAX_LINE_LENGTH - 1] = '\0';
    
    
    int field_count = 1;
    const char* ptr = line;
    while ((ptr = strchr(ptr, ',')) != NULL) {
        field_count++;
        ptr++;
    }
    
    
    data_line->fields = (char**)malloc(field_count * sizeof(char*));
    if (!data_line->fields) return INP_ERROR_MEMORY_ALLOCATION;
    
    
    char work_line[MAX_LINE_LENGTH];
    strncpy(work_line, line, MAX_LINE_LENGTH - 1);
    work_line[MAX_LINE_LENGTH - 1] = '\0';
    
    int current_field = 0;
    char* token = strtok(work_line, ",");
    
    while (token != NULL && current_field < field_count) {
        
        char* trimmed = trim_whitespace(token);
        data_line->fields[current_field] = (char*)malloc(strlen(trimmed) + 1);
        if (!data_line->fields[current_field]) {
            
            for (int i = 0; i < current_field; i++) {
                free(data_line->fields[i]);
            }
            free(data_line->fields);
            return INP_ERROR_MEMORY_ALLOCATION;
        }
        
        strcpy(data_line->fields[current_field], trimmed);
        current_field++;
        token = strtok(NULL, ",");
    }
    
    data_line->field_count = current_field;
    return INP_SUCCESS;
}


static void free_data_line(inp_data_line_t* data_line) {
    if (data_line && data_line->fields) {
        for (int i = 0; i < data_line->field_count; i++) {
            if (data_line->fields[i]) {
                free(data_line->fields[i]);
            }
        }
        free(data_line->fields);
        data_line->fields = NULL;
    }
}


inp_result_t inp_parse_file(const char* filepath, inp_file_t** result) {
    if (!filepath || !result) return INP_ERROR_INVALID_FORMAT;
    
    
    FILE* file = fopen(filepath, "r");
    if (!file) return INP_ERROR_FILE_NOT_FOUND;
    
    
    *result = (inp_file_t*)malloc(sizeof(inp_file_t));
    if (!*result) {
        fclose(file);
        return INP_ERROR_MEMORY_ALLOCATION;
    }
    
    
    (*result)->keywords = (inp_keyword_t*)malloc(MAX_KEYWORDS * sizeof(inp_keyword_t));
    if (!(*result)->keywords) {
        free(*result);
        fclose(file);
        return INP_ERROR_MEMORY_ALLOCATION;
    }
    
    (*result)->keyword_count = 0;
    strncpy((*result)->metadata.filename, filepath, sizeof((*result)->metadata.filename) - 1);
    (*result)->metadata.filename[sizeof((*result)->metadata.filename) - 1] = '\0';
    (*result)->metadata.total_lines = 0;
    (*result)->metadata.comment_lines = 0;
    (*result)->metadata.parse_errors[0] = '\0';
    
    
    char line[MAX_LINE_LENGTH];
    int line_number = 0;
    int current_keyword_index = -1;
    char continuation_buffer[MAX_LINE_LENGTH * 10] = {0}; 
    
    while (fgets(line, sizeof(line), file)) {
        line_number++;
        (*result)->metadata.total_lines++;
        
        
        size_t len = strlen(line);
        if (len > 0 && line[len-1] == '\n') {
            line[len-1] = '\0';
        }
        if (len > 1 && line[len-2] == '\r') {
            line[len-2] = '\0';
        }
        
        
        if (strlen(line) > MAX_LINE_LENGTH - 1) {
            snprintf((*result)->metadata.parse_errors, sizeof((*result)->metadata.parse_errors),
                    "Line %d exceeds maximum length", line_number);
            fclose(file);
            inp_free_file(*result);
            return INP_ERROR_LINE_TOO_LONG;
        }
        
        
        if (is_comment_line(line)) {
            (*result)->metadata.comment_lines++;
            continue;
        }
        
        
        char trimmed_copy[MAX_LINE_LENGTH];
        strncpy(trimmed_copy, line, sizeof(trimmed_copy) - 1);
        trimmed_copy[sizeof(trimmed_copy) - 1] = '\0';
        char* trimmed_line = trim_whitespace(trimmed_copy);
        if (strlen(trimmed_line) == 0) {
            continue;
        }
        
        
        if (is_keyword_line(trimmed_line)) {
            
            if (strlen(continuation_buffer) > 0) {
                strncat(continuation_buffer, " ", sizeof(continuation_buffer) - strlen(continuation_buffer) - 1);
                strncat(continuation_buffer, trimmed_line, sizeof(continuation_buffer) - strlen(continuation_buffer) - 1);
                trimmed_line = continuation_buffer;
            } else {
                strncpy(continuation_buffer, trimmed_line, sizeof(continuation_buffer) - 1);
                continuation_buffer[sizeof(continuation_buffer) - 1] = '\0';
            }
            
            
            if (is_continuation_line(trimmed_line)) {
                
                len = strlen(continuation_buffer);
                if (len > 0 && continuation_buffer[len-1] == ',') {
                    continuation_buffer[len-1] = ' '; 
                }
                continue;
            }
            
            
            if ((*result)->keyword_count >= MAX_KEYWORDS) {
                snprintf((*result)->metadata.parse_errors, sizeof((*result)->metadata.parse_errors),
                        "Too many keywords (max %d)", MAX_KEYWORDS);
                fclose(file);
                inp_free_file(*result);
                return INP_ERROR_INVALID_FORMAT;
            }
            
            current_keyword_index = (*result)->keyword_count;
            inp_result_t parse_result = parse_keyword_line(continuation_buffer, 
                                      &(*result)->keywords[current_keyword_index]);
            
            if (parse_result != INP_SUCCESS) {
                snprintf((*result)->metadata.parse_errors, sizeof((*result)->metadata.parse_errors),
                        "Error parsing keyword at line %d", line_number);
                fclose(file);
                inp_free_file(*result);
                return parse_result;
            }
            
            (*result)->keywords[current_keyword_index].line_number = line_number;
            (*result)->keyword_count++;
            
            
            continuation_buffer[0] = '\0';
        }
        
        else if (current_keyword_index >= 0) {
            inp_keyword_t* current_keyword = &(*result)->keywords[current_keyword_index];
            
            
            current_keyword->data_lines = (inp_data_line_t*)realloc(
                current_keyword->data_lines,
                (current_keyword->data_line_count + 1) * sizeof(inp_data_line_t));
            
            if (!current_keyword->data_lines) {
                fclose(file);
                inp_free_file(*result);
                return INP_ERROR_MEMORY_ALLOCATION;
            }
            
            
            inp_result_t parse_result = parse_data_line(trimmed_line,
                                      &current_keyword->data_lines[current_keyword->data_line_count]);
            
            if (parse_result != INP_SUCCESS) {
                snprintf((*result)->metadata.parse_errors, sizeof((*result)->metadata.parse_errors),
                        "Error parsing data line at line %d", line_number);
                fclose(file);
                inp_free_file(*result);
                return parse_result;
            }
            
            current_keyword->data_line_count++;
        }
    }
    
    fclose(file);
    (*result)->metadata.keyword_count = (*result)->keyword_count;
    
    return INP_SUCCESS;
}


void inp_free_file(inp_file_t* file) {
    if (!file) return;
    
    if (file->keywords) {
        for (int i = 0; i < file->keyword_count; i++) {
            inp_keyword_t* keyword = &file->keywords[i];
            if (keyword->data_lines) {
                for (int j = 0; j < keyword->data_line_count; j++) {
                    free_data_line(&keyword->data_lines[j]);
                }
                free(keyword->data_lines);
            }
        }
        free(file->keywords);
    }
    
    free(file);
}


const inp_keyword_t* inp_find_keyword(const inp_file_t* file, const char* keyword_name) {
    if (!file || !keyword_name) return NULL;
    
    for (int i = 0; i < file->keyword_count; i++) {
        if (strcasecmp(file->keywords[i].name, keyword_name) == 0) {
            return &file->keywords[i];
        }
    }
    
    return NULL;
}


void inp_print_file_info(const inp_file_t* file) {
    if (!file) return;
    
    printf("=== Abaqus Input File Information ===\n");
    printf("File: %s\n", file->metadata.filename);
    printf("Total lines: %d\n", file->metadata.total_lines);
    printf("Comment lines: %d\n", file->metadata.comment_lines);
    printf("Keywords found: %d\n", file->metadata.keyword_count);
    
    if (strlen(file->metadata.parse_errors) > 0) {
        printf("Parse errors: %s\n", file->metadata.parse_errors);
    }
    
    printf("\n=== Keywords ===\n");
    for (int i = 0; i < file->keyword_count; i++) {
        const inp_keyword_t* kw = &file->keywords[i];
        printf("*%s (line %d)\n", kw->name, kw->line_number);
        
        
        for (int j = 0; j < kw->parameter_count; j++) {
            if (kw->parameters[j].has_value) {
                printf("  %s=%s\n", kw->parameters[j].name, kw->parameters[j].value);
            } else {
                printf("  %s\n", kw->parameters[j].name);
            }
        }
        
        printf("  Data lines: %d\n", kw->data_line_count);
        printf("\n");
    }
}
