import { Tag, Input, Tooltip } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import React from "react";
import type { InputRef } from "antd";

interface EditableTagGroupState {
  tags: string[];
  inputVisible: boolean;
  inputValue: string;
  editInputIndex: number;
  editInputValue: string;
  prefix: string;
}

interface EditableTagGroupProps {}

class EditableTagGroup extends React.Component<{}, EditableTagGroupState> {
  state: EditableTagGroupState = {
    tags: [],
    inputVisible: false,
    inputValue: "",
    editInputIndex: -1,
    editInputValue: "",
    prefix: `phase`,
  };

  inputRef = React.createRef<InputRef>();
  editInputRef = React.createRef<InputRef>();
  onImport = (indexIn: { value: string[] }) => {
    let tags = [];
    // const indexIn = tensorIn.component[this.props.componentIndex].index;
    console.log("import from the tensor component index", indexIn);
    for (let i = 0; i < indexIn.value.length; i++) {
      const element = indexIn.value[i];
      tags.push(element.trim());
    }
    this.setState({ tags: tags });
  };

  onFinish = () => {
    console.log("the finish from tensor index");
    return this.state.tags;
  };

  handleClose = (removedTag: string) => {
    const tags = this.state.tags.filter((tag) => tag !== removedTag);
    console.log(tags);
    this.setState({ tags });
  };

  showInput = () => {
    this.setState({ inputVisible: true }, () => this.inputRef.current?.focus());
  };

  handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    this.setState({ inputValue: e.target.value });
  };

  handleInputConfirm = () => {
    const { inputValue } = this.state;
    let { tags } = this.state;
    if (inputValue && tags.indexOf(inputValue) === -1) {
      tags = [...tags, inputValue];
    }
    console.log(tags);
    this.setState({
      tags,
      inputVisible: false,
      inputValue: "",
    });
  };

  handleEditInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    this.setState({ editInputValue: e.target.value });
  };

  handleEditInputConfirm = () => {
    this.setState(({ tags, editInputIndex, editInputValue }) => {
      const newTags = [...tags];
      newTags[editInputIndex] = editInputValue;

      return {
        tags: newTags,
        editInputIndex: -1,
        editInputValue: "",
      };
    });
  };

  render() {
    const {
      tags,
      inputVisible,
      inputValue,
      editInputIndex,
      editInputValue,
      prefix,
    } = this.state;
    return (
      <>
        {tags.map((tag, index) => {
          if (editInputIndex === index) {
            return (
              <Input
                ref={this.editInputRef}
                key={tag}
                size="small"
                className="tag-input"
                value={editInputValue}
                onChange={this.handleEditInputChange}
                onBlur={this.handleEditInputConfirm}
                onPressEnter={this.handleEditInputConfirm}
              />
            );
          }

          const isLongTag = tag.length > 20;

          const tagElem = (
            <Tag
              className="edit-tag"
              key={`${prefix}_index[${index}]`}
              closable={index !== -1}
              onClose={() => this.handleClose(tag)}
            >
              <span
                onDoubleClick={(e) => {
                  if (index !== 0) {
                    this.setState({
                      editInputIndex: index,
                      editInputValue: tag,
                    });
                    e.preventDefault();
                  }
                }}
              >
                {isLongTag ? `${tag.slice(0, 20)}...` : tag}
              </span>
            </Tag>
          );
          return isLongTag ? (
            <Tooltip title={tag} key={tag}>
              {tagElem}
            </Tooltip>
          ) : (
            tagElem
          );
        })}
        {inputVisible && (
          <Input
            ref={this.inputRef}
            type="text"
            className="tag-input"
            value={inputValue}
            onChange={this.handleInputChange}
            onBlur={this.handleInputConfirm}
            onPressEnter={this.handleInputConfirm}
          />
        )}
        {!inputVisible && (
          <Tag className="site-tag-plus" onClick={this.showInput}>
            <PlusOutlined /> New Index
          </Tag>
        )}
      </>
    );
  }
}

export { EditableTagGroup };
