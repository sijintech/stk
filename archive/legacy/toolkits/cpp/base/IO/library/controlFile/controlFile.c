#include "niobasic/controlFile.h"
#include <ntextutils/ntextutils.h>
#if defined(_MSC_VER)
#include <io.h>
#else
#include <unistd.h>
#endif
#include <stdio.h>
#include <string.h>
#include <zf_log.h>

int n_ControlFile_node_exist_by_xpath(xmlDocPtr doc, const char* xpathText)
{
    xmlXPathContextPtr context;
    xmlXPathObjectPtr result;
    xmlChar* xpath = (xmlChar*)xpathText;
    context = xmlXPathNewContext(doc);
    if (context == NULL)
    {
        ZF_LOGE("Error in xmlXPathNewContext");
        return 0;
    }
    result = xmlXPathEvalExpression(xpath, context);
    if (result == NULL)
    {
        ZF_LOGE("Error in xmlXPathEvalExpression");
        return 0;
    }
    if (xmlXPathNodeSetIsEmpty(result->nodesetval))
    {
        // xmlXPathFreeObject(result);
        ZF_LOGI("The xpath expression %s found nothing.", xpathText);
        return 0;
    }
    xmlXPathFreeContext(context);
    return 1;
}

xmlNodePtr find_node(xmlNodePtr node, char* name)
{
    xmlNodePtr result;

    if (node == NULL)
        return NULL;

    while (node)
    {
        if ((node->type == XML_ELEMENT_NODE) &&
            (strcmp((char*)node->name, name) == 0))
        {
            return node;
        }
        if ((result = find_node(node->children, name)))
            return result;
        node = node->next;
    }

    return NULL;
}

xmlNodeSetPtr n_ControlFile_get_nodeset_by_xpath(xmlDocPtr doc,
                                                 const char* xpathText)
{
    xmlXPathContextPtr context;
    xmlXPathObjectPtr result;
    xmlChar* xpath = (xmlChar*)xpathText;
    xmlNodeSetPtr nodeset;
    if (n_ControlFile_node_exist_by_xpath(doc, xpathText))
    {
        context = xmlXPathNewContext(doc);
        result = xmlXPathEvalExpression(xpath, context);
        nodeset = result->nodesetval;
    }
    else
    {
        nodeset = NULL;
    }
    return nodeset;
}

int n_ControlFile_get_nodeset_count_by_xpath(xmlDocPtr doc,
                                             const char* xpathText)
{
    int count = 0;
    xmlNodeSetPtr nodeset = n_ControlFile_get_nodeset_by_xpath(doc, xpathText);
    if (nodeset != NULL)
    {
        count = nodeset->nodeNr;
    }
    return count;
}

xmlNodePtr n_ControlFile_get_nth_nodeset_by_xpath(xmlDocPtr doc,
                                                  const char* xpathText,
                                                  int index)
{
    xmlNodePtr node;
    xmlNodeSetPtr nodeset = n_ControlFile_get_nodeset_by_xpath(doc, xpathText);
    int count = n_ControlFile_get_nodeset_count_by_xpath(doc, xpathText);
    if (index < count)
    {
        node = nodeset->nodeTab[index];
    }
    else
    {
        ZF_LOGE("The index %i is larger than total %i of the %s", index, count,
                xpathText);
        node = NULL;
    }
    return node;
}

char* n_ControlFile_get_text_by_xpath(char* out, xmlDocPtr doc,
                                      const char* xpathText,
                                      const char* meaning)
{
    xmlXPathContextPtr context;
    xmlXPathObjectPtr result;
    xmlChar* xpath = (xmlChar*)xpathText;
    xmlNodeSetPtr nodeset;
    xmlChar* keyword;

    context = xmlXPathNewContext(doc);
    strcpy(out, "");
    if (context == NULL)
    {
        ZF_LOGE("Error in xmlXPathNewContext");
        return out;
    }
    result = xmlXPathEvalExpression(xpath, context);
    if (result == NULL)
    {
        ZF_LOGE("Error in xmlXPathEvalExpression");
        return out;
    }
    if (xmlXPathNodeSetIsEmpty(result->nodesetval))
    {
        // xmlXPathFreeObject(result);
        ZF_LOGI("The xpath expression %s found nothing.", xpathText);
        return out;
    }
    nodeset = result->nodesetval;
    if (nodeset->nodeTab[0]->xmlChildrenNode == NULL)
    {
        ZF_LOGE("The xpath %s, has no content", xpathText);
        return out;
    }
    else if (nodeset->nodeNr > 1)
    {
        ZF_LOGE(
            "You have more than one element for xpath %s, you need to be more "
            "specific.",
            xpathText);
        keyword =
            xmlNodeListGetString(doc, nodeset->nodeTab[0]->xmlChildrenNode, 1);
    }
    else
    {
        keyword =
            xmlNodeListGetString(doc, nodeset->nodeTab[0]->xmlChildrenNode, 1);
    }
    n_string_trim((char*)keyword, NULL);
    ZF_LOGI("   Key: %-50s Value: %-10s Meaning: %-20s", xpathText, keyword,
            meaning);
    strcpy(out, (char*)keyword);
    return out;
}

int n_ControlFile_get_int_by_xpath(xmlDocPtr doc, const char* xpathText,
                                   const char* meaning, int de)
{
    char text[MAX_STRING];
    n_ControlFile_get_text_by_xpath(text, doc, xpathText, meaning);
    int out = -99;
    if (text[0] != '\0')
    {
        out = strtol(text, NULL, 0);
    }
    else
    {
        ZF_LOGI("Using default value for %s: %i", xpathText, de);
        out = de;
    }
    // ZF_LOGV("Int xpath text: %s, %d",text,out);
    // free(text);
    return out;
}

short n_ControlFile_get_short_by_xpath(xmlDocPtr doc, const char* xpathText,
                                       const char* meaning, short de)
{
    char text[MAX_STRING];
    n_ControlFile_get_text_by_xpath(text, doc, xpathText, meaning);
    short out = 0;
    if (text[0] != '\0')
    {
        out = (short)atoi(text);
    }
    else
    {
        ZF_LOGI("Using default value for %s: %hu", xpathText, de);
        out = de;
    }
    // ZF_LOGV("Int xpath text: %s, %d",text,out);
    // free(text);
    return out;
}

double n_ControlFile_get_double_by_xpath(xmlDocPtr doc, const char* xpathText,
                                         const char* meaning, double de)
{
    char text[MAX_STRING];
    n_ControlFile_get_text_by_xpath(text, doc, xpathText, meaning);
    double out = -99;
    if (text[0] != '\0')
    {
        out = strtod(text, NULL);
    }
    else
    {
        ZF_LOGI("Using default value for %s: %f", xpathText, de);
        out = de;
    }
    // ZF_LOGV("Double xpath text: %s, %f",text,out);
    return out;
}

int n_ControlFile_get_bool_by_xpath(xmlDocPtr doc, const char* xpathText,
                                    const char* meaning, int de)
{
    char text[MAX_STRING];
    n_ControlFile_get_text_by_xpath(text, doc, xpathText, meaning);
    int out = 0;
    if (text[0] != '\0')
    {
        out = strtol(text, NULL, 0);
    }
    else
    {
        ZF_LOGI("Using default value for %s: %i", xpathText, de);
        out = de;
    }
    if (out != 0)
    {
        out = 1;
    }
    // ZF_LOGV("Bool xpath text: %s, %d",text,out);
    // free(text);
    return out;
}

ControlFilePtr n_ControlFile_init(const char* fileName, const char* rootName)
{
    ControlFilePtr cf;
    // NIOBASICError errOut=NIOBASIC_ERR_GOOD;
    xmlDocPtr doc = NULL;
    xmlNodePtr root = NULL;

#ifdef _MSC_VER
    if (_access(fileName, 0) != -1) // F_OK for unix, 0 for windows
#else
    if (access(fileName, F_OK) != -1) // F_OK for unix, 0 for windows
#endif
    {
        // File exist, we need to find the
        doc = xmlReadFile(fileName, NULL, 0);
        if (doc == NULL)
        {
            printf("Could not parse the XML file");
            // errOut=NIOBASIC_ERR_XMLFILEMISSING;
        }
        root = xmlDocGetRootElement(doc);
    }
    else
    {
        // ZF_LOGD("size of control file %lu %s", sizeof(ControlFile),
        // fileName); File does not exist, we need to setup one
        doc = xmlNewDoc(BAD_CAST "1.0");
        // ZF_LOGD("test");
        root = xmlNewNode(NULL, BAD_CAST rootName);
        xmlDocSetRootElement(doc, root);
    }

    cf = (ControlFilePtr)malloc(sizeof(ControlFile));
    memset(cf, 0, sizeof(ControlFile));

    cf->doc = doc;
    cf->root = root;

    xmlIndentTreeOutput = 1;
    xmlKeepBlanksDefault(0);
    return cf;
}

void n_ControlFile_free(ControlFilePtr control)
{
    xmlFreeDoc(control->doc);
    xmlCleanupParser();
    xmlMemoryDump();
    // free(control);
}

int n_get_xml_element_count(const char* fileName, const char* xpathText,
                            const char* meaning)
{
    ControlFilePtr control = n_ControlFile_init(fileName, NULL);
    int out;

    out = n_ControlFile_get_nodeset_count_by_xpath(control->doc, xpathText);

    n_ControlFile_free(control);
    return out;
}

int n_get_xml_element_count_from_memory(const char* memory,
                                        const char* xpathText,
                                        const char* meaning)
{
    xmlDocPtr doc = xmlReadMemory(memory, strlen(memory), NULL, "UTF-8", 0);

    int out;

    out = n_ControlFile_get_nodeset_count_by_xpath(doc, xpathText);
    xmlFreeDoc(doc);

    return out;
}

int n_get_xml_element_as_int_f(const char* fileName, const char* xpathText,
                               const char* meaning, int* de)
{
    return n_get_xml_element_as_int(fileName, xpathText, meaning, *de);
}
int n_get_xml_element_as_int(const char* fileName, const char* xpathText,
                             const char* meaning, int de)
{
    ControlFilePtr control = n_ControlFile_init(fileName, NULL);
    int out;
    out = n_ControlFile_get_int_by_xpath(control->doc, xpathText, meaning, de);
    n_ControlFile_free(control);
    return out;
}

short n_get_xml_element_as_short_f(const char* fileName, const char* xpathText,
                                   const char* meaning, short* de)
{
    return n_get_xml_element_as_short(fileName, xpathText, meaning, *de);
}
short n_get_xml_element_as_short(const char* fileName, const char* xpathText,
                                 const char* meaning, short de)
{
    ControlFilePtr control = n_ControlFile_init(fileName, NULL);
    short out;
    out =
        n_ControlFile_get_short_by_xpath(control->doc, xpathText, meaning, de);
    n_ControlFile_free(control);
    return out;
}

double n_get_xml_element_as_double_f(const char* fileName,
                                     const char* xpathText, const char* meaning,
                                     double* de)
{
    return n_get_xml_element_as_double(fileName, xpathText, meaning, *de);
}
double n_get_xml_element_as_double(const char* fileName, const char* xpathText,
                                   const char* meaning, double de)
{
    ControlFilePtr control = n_ControlFile_init(fileName, NULL);
    double out;
    out =
        n_ControlFile_get_double_by_xpath(control->doc, xpathText, meaning, de);
    n_ControlFile_free(control);
    return out;
}

char* n_get_xml_element_as_string(char* out, const char* fileName,
                                  const char* xpathText, const char* meaning,
                                  const char* de)
{
    ControlFilePtr control = n_ControlFile_init(fileName, NULL);
    char temp[MAX_STRING];
    n_ControlFile_get_text_by_xpath(temp, control->doc, xpathText, meaning);
    if (temp[0] == '\0')
    {
        strcpy(out, de);
        ZF_LOGI("Using default value for %s: %s", xpathText, de);
    }
    else
    {
        strcpy(out, temp);
    }
    n_ControlFile_free(control);
    return out;
}

char* n_get_xml_element_as_string_from_memory(char* out, const char* memory,
                                              const char* xpathText,
                                              const char* meaning)
{
    xmlDocPtr doc = xmlReadMemory(memory, strlen(memory), NULL, "UTF-8", 0);
    // ZF_LOGD("get text memeory, %s",memory);
    char temp[MAX_STRING];
    n_ControlFile_get_text_by_xpath(temp, doc, xpathText, meaning);
    strcpy(out, temp);
    xmlFreeDoc(doc);
    return out;
}

xmlNodePtr n_ControlFile_create_node_by_XPATH(xmlDocPtr doc, const char* xpath)
{
    // char *rewxpath = strdup(xpath);
    // rewxpath = n_string_trim(rewxpath, "\n\t\f\v /");
    // NStringArray arr=n_string_split(rewxpath,"/");
    NString last = n_string_split_last_by_index(xpath, "/");
    NString previous = n_string_split_previous_by_index(xpath, "/");
    xmlNodePtr node;
    // This is for normal, mode=0 for unique, mode=1 for append
    // xmlNodePtr node = find_node(parent, first.data);
    if (n_ControlFile_node_exist_by_xpath(doc, previous.data) != 1 &&
        previous.data[0] != '\0')
    {
        NString pprevious =
            n_string_split_previous_by_index(previous.data, "[");
        if (pprevious.data[0] != '\0')
        {
            n_ControlFile_create_node_by_XPATH(doc, pprevious.data);
        }
        else
        {
            n_ControlFile_create_node_by_XPATH(doc, previous.data);
        }
    }

    if (n_ControlFile_get_nodeset_count_by_xpath(doc, previous.data) == 1)
    {
        xmlNodePtr parent =
            n_ControlFile_get_nth_nodeset_by_xpath(doc, previous.data, 0);
        ZF_LOGI("create node '%s' under '%s'", last.data, previous.data);
        if (last.data[0] != '\0')
        {
            node = xmlNewChild(parent, NULL, BAD_CAST last.data, NULL);
            return node;
        }
        else
        {
            return parent;
        }
    }
    else
    {
        ZF_LOGI("The xpath '%s' is not unique", previous.data);
        return NULL;
    }

    // return node;
    // if (node == NULL && rest.length > 0) {
    //   node = xmlNewChild(parent, NULL, BAD_CAST first.data, NULL);
    // } else if (rest.length == 0 && (node == NULL || mode == 1)) {
    //   node = xmlNewTextChild(parent, NULL, BAD_CAST first.data, BAD_CAST
    //   input);
    // } else {
    //   ZF_LOGI("node already exist %s", xpath);
    //   // xmlNodeSetContent(node, (xmlChar *)input);
    // }
    // // ZF_LOGD("create node %s, %s, %s",rewxpath,first.data,rest.data);
    // if (rest.length == 0) {
    //   // This is for the last one
    //   // ZF_LOGD("no rest %s",first.data);
    //   return parent;
    // }
    // return n_ControlFile_create_node_by_XPATH(doc, node, rest.data, input,
    // mode);
}

void n_ControlFile_set_text_by_XPATH(xmlDocPtr doc, const char* xpathText,
                                     const char* input)
{
    xmlNodePtr node = n_ControlFile_get_nth_nodeset_by_xpath(doc, xpathText, 0);
    xmlNodeSetContent(node, (xmlChar*)input);
}

void n_set_xml_element_by_string_f(char* input, const char* fileName,
                                   const char* xpathText, const char* meaning)
{
    n_set_xml_element_by_string(input, fileName, xpathText, meaning);
}
void n_set_xml_element_by_string(char* input, const char* fileName,
                                 const char* xpathText, const char* meaning)
{
    char* rewxpath = strdup(xpathText);
    n_string_trim(rewxpath, "\n\t\f\v /");
    NStringArray arr = n_string_split(rewxpath, "/");
    char* root = arr.data[0];
    ControlFilePtr cf = n_ControlFile_init(fileName, root);
    xmlNodePtr node = n_ControlFile_create_node_by_XPATH(cf->doc, xpathText);
    xmlNodeSetContent(node, (xmlChar*)input);
    // create_node_XPATH(cf->doc, cf->root, xpathText, input, mode);
    xmlSaveFormatFile(fileName, cf->doc, 1);
    // n_ControlFile_print_node(cf->root,1);
    n_ControlFile_free(cf);
}

void n_set_xml_element_by_string_to_memory(char* input, char* output,
                                           const char* xpathText,
                                           const char* meaning)
{
    char* rewxpath = strdup(xpathText);
    xmlChar* xmlbuff;
    int buffersize;
    n_string_trim(rewxpath, "\n\t\f\v /");
    NStringArray arr = n_string_split(rewxpath, "/");
    char* root = arr.data[0];
    xmlDocPtr doc;
    xmlNodePtr n;
    if (output[0] == '\0')
    {
        doc = xmlNewDoc(BAD_CAST "1.0");
        n = xmlNewNode(NULL, BAD_CAST root);
        xmlDocSetRootElement(doc, n);
    }
    else
    {
        doc = xmlReadMemory(output, strlen(output), NULL, "UTF-8", 0);
        n = xmlDocGetRootElement(doc);
    }
    xmlNodePtr node = n_ControlFile_create_node_by_XPATH(doc, xpathText);
    xmlNodeSetContent(node, (xmlChar*)input);
    // create_node_XPATH(doc, n, xpathText, input, mode);
    xmlDocDumpMemoryEnc(doc, &xmlbuff, &buffersize, "UTF-8");
    strcpy(output, (char*)xmlbuff);
    xmlFree(xmlbuff);
    xmlFreeDoc(doc);
    // n_ControlFile_print_node(cf->root,1);
}

int is_leaf(xmlNode* node)
{
    xmlNode* child = node->children;
    while (child)
    {
        if (child->type == XML_ELEMENT_NODE)
            return 0;

        child = child->next;
    }

    return 1;
}

void n_ControlFile_print_node(xmlNode* node, int indent_len)
{
    while (node)
    {
        if (node->type == XML_ELEMENT_NODE)
        {
            printf("%*c%s:%s\n", indent_len * 2, '-', node->name,
                   is_leaf(node) ? xmlNodeGetContent(node)
                                 : xmlGetProp(node, BAD_CAST "id"));
        }
        n_ControlFile_print_node(node->children, indent_len + 1);
        node = node->next;
    }
}

NStringArray n_get_xml_element_as_NStringArray(const char* fileName,
                                               const char* xpathText,
                                               const char* meaning)
{
    NStringArray output;
    output.length = 0;

    ControlFilePtr cf = n_ControlFile_init(fileName, NULL);
    char newxpath[MAX_STRING];
    n_string_join(newxpath, xpathText, "value", "/");
    // ZF_LOGD("JOIN CHAR %s,%s",newxpath,xpathText);
    xmlNodeSetPtr array = n_ControlFile_get_nodeset_by_xpath(cf->doc, newxpath);
    if (array != NULL)
    {
        size_t i = 0;
        output.length = array->nodeNr;
        for (i = 0; i < array->nodeNr; i++)
        {
            // ZF_LOGD("length of nodeset %i, %i",i,output.length);
            strcpy(output.data[i],
                   (char*)xmlNodeListGetString(
                       cf->doc, array->nodeTab[i]->xmlChildrenNode, 1));
        }
    }
    n_ControlFile_free(cf);
    return output;
}

NStringArray n_get_xml_element_as_NStringArray_from_memory(
    const char* memory, const char* xpathText, const char* meaning)
{
    NStringArray output;
    output.length = 0;
    char newxpath[MAX_STRING];
    n_string_join(newxpath, xpathText, "value", "/");
    xmlDocPtr doc = xmlReadMemory(memory, strlen(memory), NULL, "UTF-8", 0);

    // ZF_LOGD("JOIN CHAR %s,%s",newxpath,xpathText);
    xmlNodeSetPtr array = n_ControlFile_get_nodeset_by_xpath(doc, newxpath);
    if (array != NULL)
    {
        output.length = array->nodeNr;
        size_t i = 0;
        for (i = 0; i < array->nodeNr; i++)
        {
            // ZF_LOGD("length of nodeset %i, %i",i,output.length);
            strcpy(output.data[i],
                   (char*)xmlNodeListGetString(
                       doc, array->nodeTab[i]->xmlChildrenNode, 1));
        }
    }
    xmlFreeDoc(doc);
    return output;
}

void n_set_xml_element_by_NStringArray(NStringArray input, const char* fileName,
                                       const char* xpathText,
                                       const char* meaning)
{
    char newxpath[MAX_STRING];
    n_string_join(newxpath, xpathText, "value", "/");
    size_t i = 0;
    for (i = 0; i < input.length; i++)
    {
        n_set_xml_element_by_string(input.data[i], fileName, newxpath, meaning);
    }
    if (input.length == 0)
    {
        n_set_xml_element_by_string("", fileName, xpathText, meaning);
    }
}

void n_set_xml_element_by_NStringArray_to_memory(NStringArray input,
                                                 char* output,
                                                 const char* xpathText,
                                                 const char* meaning)
{
    char newxpath[MAX_STRING];
    n_string_join(newxpath, xpathText, "value", "/");
    // ZF_LOGD("set text memeory,%s, %s",output,newxpath);
    size_t i = 0;
    for (i = 0; i < input.length; i++)
    {

        // ZF_LOGD("super text memeory,%i, %s",i,output );

        n_set_xml_element_by_string_to_memory(input.data[i], output, newxpath,
                                              meaning);
    }
    if (input.length == 0)
    {
        n_set_xml_element_by_string_to_memory("", output, xpathText, meaning);
    }
}

void n_set_xml_element_by_double_f(double* input, const char* fileName,
                                   const char* xpathText, const char* meaning)
{
    n_set_xml_element_by_double(*input, fileName, xpathText, meaning);
}
void n_set_xml_element_by_double(double input, const char* fileName,
                                 const char* xpathText, const char* meaning)
{
    char inputText[MAX_STRING] = {0};
    sprintf(inputText, MY_XML_FORMAT_SCIENTIFIC, input);
    n_set_xml_element_by_string(inputText, fileName, xpathText, meaning);
}

void n_set_xml_element_by_int_f(int* input, const char* fileName,
                                const char* xpathText, const char* meaning)
{
    n_set_xml_element_by_int(*input, fileName, xpathText, meaning);
}
void n_set_xml_element_by_int(int input, const char* fileName,
                              const char* xpathText, const char* meaning)
{
    char inputText[MAX_STRING] = {0};
    sprintf(inputText, MY_XML_FORMAT_INT, input);
    n_set_xml_element_by_string(inputText, fileName, xpathText, meaning);
}