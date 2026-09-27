//#define _CRT_SECURE_NO_WARNINGS
#define _CRT_NONSTDC_NO_DEPRECATE

#include "ntextutils/ntextutils.h"

char *n_convert_int_to_string(char *out, int number)
{
  sprintf(out, "%i", number);
  return out;
}

int n_string_exist(const char *base, const char *comp)
{
  int out = 0;
  size_t i = 0;
  for (i = 0; i <= strlen(base) - strlen(comp); i++)
  {
    if (strncmp(base + i, comp, strlen(comp)) == 0)
    {
      out = 1;
    }
  }
  return out;
}

int n_char_exist(const char *base, char comp)
{
  int out = 0;
  size_t i = 0;
  for (i = 0; i < strlen(base); i++)
  {
    if (base[i] == comp)
    {
      out = 1;
    }
  }
  return out;
}

int n_string_count(const char *base, const char *comp)
{
  int i, j, found, count;
  int stringLen, searchLen;

  stringLen = strlen(base); // length of string
  searchLen = strlen(comp); // length of word to be searched

  count = 0;

  for (i = 0; i <= stringLen - searchLen; i++)
  {
    /* Match word with string */
    found = 1;
    for (j = 0; j < searchLen; j++)
    {
      if (base[i + j] != comp[j])
      {
        found = 0;
        break;
      }
    }

    if (found == 1)
    {
      count++;
    }
  }

  return count;
}

// #define SWP(x,y) (x^=y, y^=x, x^=y)

// void strrev(char *p)
// {
//   char *q = p;
//   while(q && *q) ++q; /* find eos */
//   for(--q; p < q; ++p, --q) SWP(*p, *q);
// }

// void strrev_utf8(char *p)
// {
//   char *q = p;
//   strrev(p); /* call base case */

//   /* Ok, now fix bass-ackwards UTF chars. */
//   while(q && *q) ++q; /* find eos */
//   while(p < --q)
//     switch( (*q & 0xF0) >> 4 ) {
//     case 0xF: /* U+010000-U+10FFFF: four bytes. */
//       SWP(*(q-0), *(q-3));
//       SWP(*(q-1), *(q-2));
//       q -= 3;
//       break;
//     case 0xE: /* U+000800-U+00FFFF: three bytes. */
//       SWP(*(q-0), *(q-2));
//       q -= 2;
//       break;
//     case 0xC: /* fall-through */
//     case 0xD: /* U+000080-U+0007FF: two bytes. */
//       SWP(*(q-0), *(q-1));
//       q--;
//       break;
//     }
// }

void n_string_reverse_in_place(char *head)
{
  if (!head)
    return;
  char *tail = head;
  while (*tail)
    ++tail; // find the 0 terminator, like head+strlen
  --tail;   // tail points to the last real char
            // head still points to the first
  for (; head < tail; ++head, --tail)
  {
    // walk pointers inwards until they meet or cross in the middle
    char h = *head, t = *tail;
    *head = t; // swapping as we go
    *tail = h;
  }
}

NString n_string_split_first_by_token(const char *a, const char *delim)
{
  char *token1;
  char *first = strdup(a);
  token1 = strtok(first, delim);
  NString output = n_NString_init(token1);
  return output;
}

NString n_string_split_rest_by_token(const char *a, const char *delim)
{
  char *token2;
  char *first = strdup(a);
  strtok(first, delim);
  token2 = strtok(NULL, "\0");
  NString output = n_NString_init(token2);
  return output;
}

NString n_string_split_first_by_index(const char *a, const char *delim)
{
  int index = n_substring_index(a, delim);
  NString output;
  if (index == -1)
  {
    output = n_NString_init(a);
  }
  else
  {
    char first[MAX_STRING] = {0};
    strncpy(first, a, index);
    output = n_NString_init(first);
  }
  return output;
}

NString n_string_split_rest_by_index(const char *a, const char *delim)
{
  int index = n_substring_index(a, delim);
  NString output;
  if (index == -1)
  {
    output = n_NString_init("");
  }
  else
  {
    int length = strlen(a);
    // char *rest = strndup(a+index+1,length-index-1);
    char rest[MAX_STRING] = {0};
    strncpy(rest, a + index + 1, length - index - 1);
    output = n_NString_init(rest);
  }
  return output;
}

NString n_string_split_last_by_index(const char *a, const char *delim)
{
  char *text = strdup(a);
  char *miled = strdup(delim);
  n_string_reverse_in_place(text);
  n_string_reverse_in_place(miled);
  NString output = n_string_split_first_by_index(text, miled);
  n_string_reverse_in_place(output.data);
  return output;
}

NString n_string_split_previous_by_index(const char *a, const char *delim)
{
  char *text = strdup(a);
  char *miled = strdup(delim);
  n_string_reverse_in_place(text);
  n_string_reverse_in_place(miled);
  NString output = n_string_split_rest_by_index(text, miled);
  n_string_reverse_in_place(output.data);
  return output;
}

NString n_string_split_last_by_token(const char *a, const char *delim)
{
  char *text = strdup(a);
  char *miled = strdup(delim);
  n_string_reverse_in_place(text);
  n_string_reverse_in_place(miled);
  NString output = n_string_split_first_by_token(text, miled);
  n_string_reverse_in_place(output.data);
  return output;
}

NString n_string_split_previous_by_token(const char *a, const char *delim)
{
  char *text = strdup(a);
  char *miled = strdup(delim);
  n_string_reverse_in_place(text);
  n_string_reverse_in_place(miled);
  NString output = n_string_split_rest_by_token(text, miled);
  n_string_reverse_in_place(output.data);
  return output;
}

NStringArray n_string_split(const char *a_str, const char *delim)
{
  NStringArray result;
  // NStringArray test; //This is important
  // result=&test;
  size_t count = 0;
  char *tmp = strdup(a_str);
  char *tmp1 = strdup(a_str);
  // char* last_comma = 0;

  // printf("a_Str=%s\n",a_str);
  // printf("tmp=%s\n",tmp);
  // printf("delim=%s\n",delim);
  // printf("tmp1=%s\n",tmp1);
  /* Count how many elements will be extracted. */
  while (*tmp)
  {
    if (n_char_exist(delim, tmp[0]))
    {
      count++;
      // last_comma = tmp;
    }
    tmp++;
  }
  // printf("after something %s,%s\n",last_comma, (a_str + strlen(a_str) - 1));

  /* Add space for trailing token. */
  // count += last_comma[0] == (a_str + strlen(a_str) - 1)[0];
  /* Add space for terminating null string so caller
     knows where the list of returned strings ends. */
  count++;

  result.length = count;

  // printf("Count of string split, %lu,%lu\n",result->length,count);

  size_t idx = 0;
  if (n_char_exist(delim, tmp1[0]))
    idx = 1;
  char *token = strtok(tmp1, delim);

  while (token)
  {
    memset(result.data[idx], '\0', MAX_STRING * sizeof(char));
    assert(idx < count);
    strcpy(result.data[idx], strdup(token));
    idx++;
    token = strtok(0, delim);
  }

  return result;
}

// char *n_char_pickup(const char *a_str, const char *delim) {
//   char *result;
//   size_t count = 0;
//   char *tmp = strdup(a_str);
//   // char* tmp1       = strdup(a_str);
//   // char* last_comma = 0;

//   /* Count how many elements will be extracted. */
//   memset(result, '\0', MAX_STRING * sizeof(char));
//   while (*tmp) {
//     if (strchr(delim, *tmp)) {
//       result[count] = *tmp;
//       // count++;
//     }
//     tmp++;
//   }
//   return result;
// }

int n_substring_index(const char *input, const char *sub)
{
  char *base = strdup(input);
  char *result = strstr(base, sub);
  if (result != NULL)
  {
    return result - base;
  }
  else
  {
    return -1;
  }
}

char *n_string_trim_left(char *inout, const char *seps)
{
  size_t totrim;
  if (seps == NULL)
  {
    seps = "\t\n\v\f\r ";
  }
  totrim = strspn(inout, seps);
  if (totrim > 0)
  {
    size_t len = strlen(inout);
    if (totrim == len)
    {
      inout[0] = '\0';
    }
    else
    {
      memmove(inout, inout + totrim, len + 1 - totrim);
    }
  }
  return inout;
}

char *n_string_trim_right(char *inout, const char *seps)
{
  int i;
  if (seps == NULL)
  {
    seps = "\t\n\v\f\r ";
  }
  i = strlen(inout) - 1;
  while (i >= 0 && strchr(seps, inout[i]) != NULL)
  {
    inout[i] = '\0';
    i--;
  }
  return inout;
}

char *n_string_trim(char *inout, const char *seps)
{
  return n_string_trim_left(n_string_trim_right(inout, seps), seps);
}

void n_file_append_string(const char *fileName, const char *content)
{
  FILE *fp;
  fp = fopen(fileName, "a");
  fputs(content, fp);
  fclose(fp);
}

void n_file_write_string(const char *fileName, const char *content)
{
  FILE *fp;
  fp = fopen(fileName, "w");
  fputs(content, fp);
  fclose(fp);
}

void n_file_write_fix_length_string(const char *fileName, const char *content,
                                    size_t length)
{
  FILE *fp;
  fp = fopen(fileName, "w");
  fwrite(content, 1, length, fp);
  fclose(fp);
}

void n_file_binary_write_fix_length_string(const char *fileName, const char *content,
                                           size_t length)
{
  FILE *fp;
  fp = fopen(fileName, "wb");
  fwrite(content, 1, length, fp);
  fclose(fp);
}

char *n_file_read_string(char *out, const char *f_name)
{
  char *buffer;
  size_t length;
  FILE *f = fopen(f_name, "r");
  size_t read_length;

  if (f)
  {
    fseek(f, 0, SEEK_END);
    length = ftell(f);
    fseek(f, 0, SEEK_SET);

    // 1 GiB; best not to load a whole large file in one string
    if (length > 1073741824)
    {
      // *err = NTEXTUTILS_ERR_FILE_TO_LARGE;

      // return NULL;
    }

    buffer = (char *)calloc(length + 1, sizeof(char));

    if (length)
    {
      read_length = fread(buffer, sizeof(char), length, f);

      if (length != read_length)
      {
        //  *err = NTEXTUTILS_ERR_FILE_READ_ERROR;

        //  return NULL;
      }
    }

    fclose(f);

    // *err = NTEXTUTILS_ERR_FILE_OK;
    buffer[length] = '\0';
    // *f_size = length;
    strcpy(out, buffer);
    free(buffer);
  }
  else
  {
    // *err = NTEXTUTILS_ERR_FILE_NOT_EXIST;

    // return NULL;
  }

  return out;
}

char *n_file_read_fix_length_string(char *out, const char *f_name, size_t length)
{
  char *buffer;
  FILE *f = fopen(f_name, "r");
  size_t read_length;

  if (f)
  {

    buffer = (char *)calloc(length + 1, sizeof(char));

    if (length)
    {
      read_length = fread(buffer, sizeof(char), length, f);

      if (length != read_length)
      {
        //  *err = NTEXTUTILS_ERR_FILE_READ_ERROR;

        //  return NULL;
      }
    }

    fclose(f);

    // *err = NTEXTUTILS_ERR_FILE_OK;
    buffer[length] = '\0';
    // *f_size = length;
  }
  else
  {
    // *err = NTEXTUTILS_ERR_FILE_NOT_EXIST;

    // return NULL;
  }
  size_t i = 0;
  for (i = 0; i < length; i++)
  {
    out[i] = buffer[i];
  }

  free(buffer);

  return out;
}

char *n_file_binary_read_string(char *out, const char *f_name, size_t length)
{
  char *buffer;
  FILE *f = fopen(f_name, "rb");
  size_t read_length;

  if (f)
  {

    buffer = (char *)calloc(length, sizeof(char));

    if (length)
    {
      read_length = fread(buffer, sizeof(char), length, f);

      if (length != read_length)
      {
        //  *err = NTEXTUTILS_ERR_FILE_READ_ERROR;

        //  return NULL;
      }
    }

    fclose(f);

    // *err = NTEXTUTILS_ERR_FILE_OK;
    // *f_size = length;
  }
  else
  {
    // *err = NTEXTUTILS_ERR_FILE_NOT_EXIST;

    // return NULL;
  }
  // strncpy(out,buffer,length);
  size_t i = 0;
  for (i = 0; i < length; i++)
  {
    out[i] = buffer[i];
  }

  free(buffer);

  return out;
}

char *n_file_hex_read_string(char *out, const char *f_name, size_t length)
{
  FILE *fp = fopen(f_name, "r");
  size_t size = 0;
  unsigned int val;
  int startpos = ftell(fp);
  while (fscanf(fp, "%x ", &val) == 1)
  {
    ++size;
  }
  if (length != size)
  {
    //  *err = NTEXTUTILS_ERR_FILE_READ_ERROR;
    printf("The length is not as expected %zu %zu", length, size);
    //  return NULL;
  }
  fseek(fp, startpos, SEEK_SET);
  int pos = 0;
  while (fscanf(fp, "%x ", &val) == 1)
  {
    out[pos++] = (unsigned char)val;
  }
  return out;
}

char *n_string_join(char *output, const char *a, const char *b,
                    const char *delim)
{
  strcpy(output, a);
  strcat(output, delim);
  strcat(output, b);
  return output;
}

NString n_NString_join(NString a, NString b, const char *delim)
{
  NString output;
  strcpy(output.data, n_string_join(output.data, a.data, b.data, delim));
  output.length = a.length + b.length + strlen(delim);
  return output;
}

NString n_NStringArray_join(NStringArray a, const char *delim)
{
  char temp[MAX_STRING] = "";
  size_t i = 0;
  for (i = 0; i < a.length; i++)
  {
    strcat(temp, a.data[i]);
    if (i < a.length - 1)
    {
      strcat(temp, delim);
    }
  }
  return n_NString_init(temp);
}

int n_NStringArray_contain_string(NStringArray a, const char *b)
{
  size_t i = 0;
  for (i = 0; i < a.length; i++)
  {
    if (n_string_equal(a.data[i], b))
    {
      return 1;
    }
  }
  return 0;
}

int n_NStringArray_string_index(NStringArray a, const char *b)
{
  size_t i = 0;
  for (i = 0; i < a.length; i++)
  {
    if (n_string_equal(a.data[i], b))
    {
      return i;
    }
  }
  return -1;
}

int n_string_equal(const char *a, const char *b)
{
  int ret = strcmp(a, b);
  if (ret == 0)
  {
    return 1;
  }
  else
  {
    return 0;
  }
}

NString n_NString_init(const char *input)
{
  NString ns;
  if (input)
  {
    strcpy(ns.data, input);
    ns.length = strlen(input);
  }
  else
  {
    ns.length = 0;
    ns.data[0] = '\0';
  }
  return ns;
}

NStringPtr n_NStringPtr_init(const char *input)
{
  NStringPtr ns;
  ns = (NStringPtr)malloc(sizeof(NString));
  memset(ns, 0, sizeof(NString));
  strcpy(ns->data, input);
  ns->length = strlen(input);
  return ns;
}

void n_NStringPtr_free(NStringPtr input) { free(input); }

NStringArrayPtr n_NStringArrayPtr_init(int length)
{
  NStringArrayPtr nsa;

  nsa = (NStringArrayPtr)malloc(sizeof(NStringArray));
  memset(nsa, 0, sizeof(NStringArray));
  nsa->length = length;
  return nsa;
}

NStringArray n_NStringArray_init(int length)
{
  NStringArray nsa;
  nsa.length = length;
  return nsa;
}

void n_NStringArrayPtr_free(NStringArrayPtr input) { free(input); }

// Remeber to free the concat string
char *n_string_concat(char *out, int count, ...)
{
  va_list ap;
  int i;

  // Find required length to store merged string
  int len = 1; // room for NULL
  va_start(ap, count);
  for (i = 0; i < count; i++)
    len += strlen(va_arg(ap, char *));
  va_end(ap);

  // Allocate memory to concat strings
  char *merged = (char *)calloc(sizeof(char), len);
  int null_pos = 0;

  // Actually concatenate strings
  va_start(ap, count);
  for (i = 0; i < count; i++)
  {
    char *s = va_arg(ap, char *);
    strcpy(merged + null_pos, s);
    null_pos += strlen(s);
  }
  va_end(ap);

  strcpy(out, merged);
  free(merged);
  return out;
}

NString n_current_time_as_string()
{
  time_t cur = time(NULL);
  NString output;
#if defined(_MSC_VER)
  sprintf(output.data, "%lld", cur);
#else
  sprintf(output.data, "%ld", cur);
#endif
  return output;
}

time_t n_future_time_as_int(int futureDays)
{
  time_t cur = time(NULL);
  time_t future = cur + futureDays * 86400;
  return future;
}

NString n_future_time_as_string(int futureDays)
{
  time_t future = n_future_time_as_int(futureDays);
  NString output;
#if defined(_MSC_VER)
  sprintf(output.data, "%lld", future);
#else
  sprintf(output.data, "%ld", future);
#endif
  return output;
}

NStringArray n_double_to_NStringArray(double *input, int length,
                                      const char *format)
{
  NStringArray temp = n_NStringArray_init(length);
  size_t i = 0;
  for (i = 0; i < (size_t)length; i++)
  {
    sprintf(temp.data[i], format, input[i]);
  }
  return temp;
}