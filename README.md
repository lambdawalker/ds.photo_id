---
license: cc-by-4.0  
task_categories:
- text-to-image  
- image-to-text  
- object-detection  
language:  
- en  
tags:  
- photography  
- headshot  
- flux  
- gemma  
- synthetic  
- metadata  
- json  
- structured-data
---
# **Photo ID Dataset**

## **Overview**

The **Photo ID Dataset** is a high-quality collection of 2,000 synthetic PNG images depicting individuals in a professional ID-style headshot format. This dataset is designed to bridge the gap between high-fidelity image generation, vision-language understanding, and structured data extraction.

Each image was generated using **Flux 1** for realistic human features and subsequently processed by **Gemma 3 12B** to provide both rich natural language descriptions and structured JSON metadata containing fictional identity profiles.

## **Dataset Structure**

Each entry in the dataset contains:

* **image**: The 512x512 PNG headshot.  
* **prompt**: The original text prompt used to generate the image.  
* **description**: A dense, assertive description of the person's visual traits.  
* **file\_id**: Unique identifier for the entry.  
* **person\_metadata**: A structured JSON object containing a fictional identity.

### **Metadata Schema**

The person\_metadata field includes:

* **Identification**: First name, last name, DOB, age, gender, ethnicity.  
* **Contact Info**: Fictional address, email, and phone number.  
* **Biometric Details**: Eye color, height (cm), weight (kg), and blood type.  
* **Metadata**: Occupation, citizenship status, and document issue date.

## **Usage**

You can load this dataset using the Hugging Face datasets library:

from datasets import load\_dataset

\# Load the dataset  
dataset \= load\_dataset("lambdaWalker/photo\_id")

\# Access a sample from the 'body' split  
example \= dataset\['body'\]\[0\]

\# Display Image  
example\['image'\].show()

\# Print Structured Metadata  
meta \= example\['person\_metadata'\]  
print(f"Name: {meta\['identification'\]\['first\_name'\]} {meta\['identification'\]\['last\_name'\]}")  
print(f"Occupation: {meta\['metadata'\]\['occupation'\]}")  
print(f"Bio: {meta\['biometric\_details'\]\['height\_cm'\]}cm, {meta\['biometric\_details'\]\['weight\_kg'\]}kg")

\# Print Descriptions  
print(f"Description: {example\['description'\]}")

## **Dataset Details**

* **Total Images:** 2,000  
* **Format:** PNG (512x512 pixels)  
* **Content:** Synthetic headshots of diverse individuals (varying gender, descent, age, and style).  
* **Generation Stack:** \* **Image Gen:** Flux 1  
  * **Vision/Logic:** Gemma 3 12B  
* **Synthetic Nature:** All identities, addresses, and personal details are entirely fictional and AI-generated.

## **License**

This dataset is licensed under the **Creative Commons Attribution 4.0 International (CC BY 4.0)** license.

Attribution:  
LambdaWarker@isdavid.com  
You are free to share and adapt this material for any purpose, even commercially, provided you give appropriate credit.
