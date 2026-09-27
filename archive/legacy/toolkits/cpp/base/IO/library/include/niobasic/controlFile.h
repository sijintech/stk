/**
 * Class:
 * Description:
 * Parameters:
 * Methods:
 */

#ifndef __CONTROLFILE_H__
#define __CONTROLFILE_H__

//#define _CRT_SECURE_NO_WARNINGS
#define _CRT_NONSTDC_NO_DEPRECATE

#include "stdlib.h"
#include <libxml/parser.h>
#include <libxml/xpath.h>
#include <niobasic/errors.h>
#include <niobasic/exports.h>
#include <ntextutils/ntextutils.h>
//#include <unistd.h>
#ifdef __cplusplus
extern "C"
{
#endif

#define MY_XML_ENCODING "UTF-8"
#define MY_XML_FORMAT_SCIENTIFIC "%+13.6le"
#define MY_XML_FORMAT_DOUBLE "%+6.2f"
#define MY_XML_FORMAT_INT "%+i"

    typedef struct _ControlFile ControlFile;
    typedef ControlFile *ControlFilePtr;
    struct _ControlFile
    {
        xmlDocPtr doc;
        xmlNodePtr root;
    };

    NIOBASICPUBFUN ControlFilePtr NIOBASICCALL n_ControlFile_init(const char *fileName, const char *rootName);
    NIOBASICPUBFUN void NIOBASICCALL n_ControlFile_free(ControlFilePtr control);
    NIOBASICPUBFUN int NIOBASICCALL n_ControlFile_node_exist_by_xpath(xmlDocPtr doc, const char *xpathText);
    NIOBASICPUBFUN xmlNodeSetPtr NIOBASICCALL n_ControlFile_get_nodeset_by_xpath(xmlDocPtr doc, const char *xpathText);
    NIOBASICPUBFUN int NIOBASICCALL n_ControlFile_get_nodeset_count_by_xpath(xmlDocPtr doc, const char *xpathText);
    NIOBASICPUBFUN xmlNodePtr NIOBASICCALL n_ControlFile_get_nth_nodeset_by_xpath(xmlDocPtr doc, const char *xpathText, int index);
    NIOBASICPUBFUN xmlNodePtr NIOBASICCALL n_ControlFile_create_node_by_XPATH(xmlDocPtr doc, const char *xpath);

    NIOBASICPUBFUN void NIOBASICCALL n_ControlFile_print_node(xmlNodePtr node, int indent_len);
    NIOBASICPUBFUN char *NIOBASICCALL n_ControlFile_get_text_by_xpath(char *out, xmlDocPtr doc, const char *xpathText, const char *meaning);
    NIOBASICPUBFUN int NIOBASICCALL n_ControlFile_get_int_by_xpath(xmlDocPtr doc, const char *xpathText, const char *meaning, int de);
    NIOBASICPUBFUN short NIOBASICCALL n_ControlFile_get_short_by_xpath(xmlDocPtr doc, const char *xpathText, const char *meaning, short de);
    NIOBASICPUBFUN double NIOBASICCALL n_ControlFile_get_double_by_xpath(xmlDocPtr doc, const char *xpathText, const char *meaning, double de);
    NIOBASICPUBFUN int NIOBASICCALL n_ControlFile_get_bool_by_xpath(xmlDocPtr doc, const char *xpathText, const char *meaning, int de);

    NIOBASICPUBFUN int NIOBASICCALL n_get_xml_element_count(const char *fileName, const char *xpathText, const char *meaning);
    NIOBASICPUBFUN int NIOBASICCALL n_get_xml_element_count_from_memory(const char *memory, const char *xpathText, const char *meaning);
    NIOBASICPUBFUN int NIOBASICCALL n_get_xml_element_as_int(const char *fileName, const char *xpathText, const char *meaning, int de);
    NIOBASICPUBFUN short NIOBASICCALL n_get_xml_element_as_short(const char *fileName, const char *xpathText, const char *meaning, short de);
    // NIOBASICPUBFUN int NIOBASICCALL get_int_python(const char *fileName,const
    // char *xpathText, const char *meaning); NIOBASICPUBFUN void NIOBASICCALL
    // get_int_fortran(int *out, const char *fileName,const char *xpathText, const
    // char *meaning);

    NIOBASICPUBFUN double NIOBASICCALL n_get_xml_element_as_double(const char *fileName, const char *xpathText, const char *meaning, double de);
    // NIOBASICPUBFUN double NIOBASICCALL get_double_python(const char
    // *fileName,const char *xpathText, const char *meaning); NIOBASICPUBFUN void
    // NIOBASICCALL get_double_fortran(double *out, const char *fileName,const char
    // *xpathText, const char *meaning);

    NIOBASICPUBFUN char *NIOBASICCALL n_get_xml_element_as_string(char *out, const char *fileName, const char *xpathText, const char *meaning, const char *de);
    NIOBASICPUBFUN char *NIOBASICCALL n_get_xml_element_as_string_from_memory(char *out, const char *memory, const char *xpathText, const char *meaning);
    NIOBASICPUBFUN NStringArray NIOBASICCALL n_get_xml_element_as_NStringArray(const char *fileName, const char *xpathText, const char *meaning);
    NIOBASICPUBFUN NStringArray NIOBASICCALL n_get_xml_element_as_NStringArray_from_memory(const char *memory, const char *xpathText, const char *meaning);
    // NIOBASICPUBFUN char * NIOBASICCALL get_text_python(char *out, const char
    // *fileName,const char *xpathText, const char *meaning); NIOBASICPUBFUN void
    // NIOBASICCALL get_text_fortran(int *out, const char *fileName,const char
    // *xpathText, const char *meaning);

    NIOBASICPUBFUN void NIOBASICCALL n_set_xml_element_by_string(char *input, const char *fileName, const char *xpathText, const char *meaning);
    NIOBASICPUBFUN void NIOBASICCALL n_set_xml_element_by_string_to_memory(char *input, char *output, const char *xpathText, const char *meaning);
    NIOBASICPUBFUN void NIOBASICCALL n_set_xml_element_by_NStringArray(NStringArray input, const char *fileName, const char *xpathText, const char *meaning);
    NIOBASICPUBFUN void NIOBASICCALL n_set_xml_element_by_NStringArray_to_memory(NStringArray input, char *output, const char *xpathText, const char *meaning);

    NIOBASICPUBFUN void NIOBASICCALL n_set_xml_element_by_int(int input, const char *fileName, const char *xpathText, const char *meaning);
    NIOBASICPUBFUN void NIOBASICCALL n_set_xml_element_by_double(double input, const char *fileName, const char *xpathText, const char *meaning);

    // NIOBASICPUBFUN xmlNodePtr NIOBASICCALL get_node_xpath (xmlDocPtr doc, const
    // char *xpathText); NIOBASICPUBFUN xmlNodeSetPtr NIOBASICCALL
    // n_ControlFile_get_nodeset_by_xpath (xmlDocPtr doc, const char *xpathText);
    // NIOBASICPUBFUN xmlNodePtr NIOBASICCALL get_node(xmlNodePtr node,const char
    // *nodeName);

#ifdef __cplusplus
}
#endif

#endif /*__CONTROLFILE_H__*/
