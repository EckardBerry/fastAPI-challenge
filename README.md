# LG SQUAD Code Challenge

The Goal of this code challenge is to create a *SIMPLE* invoice management system issued to customers using FastAPI, Pydantic and SQLAlchemy. Use a MYSQL8 database setup locally with appropriate tables running on localhost (up and down scripts supplied)- It has the following credentials declared in the `.env`

```
DB_USER = "root"
DB_PASSWORD = "example"
DB_URL = "127.0.0.1:3306/invoice_management"
```

There are two endpoints that are done for you:

**GET /health-check** - will return successfully if the database is working correctly - returning

```
200, {"status":"UP"}

```

**GET invoice/{`invoice_id`}** - will read the database and return a record associated with the `invoice_id`, returning the output from a pydantic object called `InvoiceResponse`. 

Example an `invoice_id=a14e5bd8-02ce-11f0-8d97-7c646cb7c0bc` could return: 

```
200,
{
    "id": "a14e5bd8-02ce-11f0-8d97-7c646cb7c0bc",
    "jobDescription": "Software License Fee",
    "customerId": 4,
    "amount": 99.99,
    "customerName": "Amanda Lee",
    "customerEmail": "amanda.lee@paymark.co.nz",
    "invoiceStatus": "CANCELLED"
}
```


Please make sure you can get these endpoints working using POSTMAN and look carefully at the code provided to you.


There is also a mock server code called **fake_pay** - similuating a backend external payment provider (do not modify this file). Its url is given in the `.env` as:

```
FAKEPAY_URL = "http://127.0.0.1:9000/fakepay"
```
To start the fake pay service, open a new terminal and navigate to to the *fake_pay.py* and start it with:

```
python fake_pay.py
```

When provided with correct card/transactionId details declared in the structure determined by the Pydantic model `FakePayRequest`, The fake_pay service will return: 

```
200, {'message': 'Payment processed successfully'}
```

Make sure the `fake_pay.py` file remains running or if accidentally crashed or closed, restart it with standard python command above.


#### Install python venv and create virtual environment

```
python -m venv ./myenv
```

#### Run virtual environment installed:
```
../myenv/Scripts/activate
```

#### Install toml file via poetry:
If lock file created:
```
poetry lock
```
Install dependancies

```
poetry install
```


#### Recommended Python Libraries
These should already be installed via poetry and declared in the toml file - feel free to add others as needed.


#### Running the Project
To run the application (this will automatically detect changes for live code updates)

```
poetry run uvicorn src.main:app --reload
```



## YOUR TASK: 

Create the following three endpoints:


### 1) POST: /invoice
Creates an 'InvoiceRequest' for a customer (represented with an integer `customerId`), it should create a new `id` for the invoice and persist it in the database, assuming the customerId exists in the customer table. It then should formulate the following output response  - handling any issues where the customerId is not found.

Example the following request loaded into a pydantic `InvoiceRequest`:

```
{
    "jobDescription": "Software Development and Testing",
    "amount": 199.99,
    "customerId": 2
}
```

Should produce the `InvoiceResponse` output:

```
201, {
    "id": "8176929e-5484-462b-9758-c74ac68f7892",
    "jobDescription": "Software Development and Testing",
    "customerId": 2,
    "amount": 199.99,
    "customerName": "Jane Smith",
    "customerEmail": "jane.smith@example.com",
    "invoiceStatus": "PENDING"
}
```

Modify further so that an optional `Card` object can be used to pay the invoice, if no card is provided it should leave the invoice in a PENDING state. A payment can be made using a `FakePayRequest` (pydantic model included) to the mock Fakepay server, its `transactionId` should match the invoice `id`. It should then set the `invoiceStatus` to PAID assuming FakePay returned a 200 result. The response back to the client should include the `Card` object in a masked format. 

EG: An 'InvoiceRequest` of:

```
{
    "jobDescription": "Software License Fee",
    "amount": 99.99,
    "customerId": 1,
    "card": {
        "number": "1234567812345678",
        "name": "J Doe",
        "expiry": "01-2040"
    }
}
```

Assuming *FakePay* called correctly should produce the `InvoiceResponse':

```
201,
{
    "id": "8176929e-5484-462b-9758-c74ac68f7892",
    "jobDescription": "Software License Fee",
    "customerId": 1,
    "amount": 99.99,
    "card": {
        "number": "123456********5678",
        "expiry": "01-2040",
        "name": "J Doe"
    },
    "customerName": "John Doe",
    "customerEmail": "john.doe@example.com",
    "invoiceStatus": "PAID"
}
```
If you are unsure about the Card payment step, move to task 2 first then come back to it. Note `InvoiceRequest` and `InvoiceResponse` have been provided but may not be fully complete - depending on how you go about accomplishing the tasks.



### 2) POST: /invoice/pay/{`invoice_id`}
Create another endpoint that pays any PENDING invoice using the `Card` object structure.  For example
if the `invoice_id=8176929e-5484-462b-9758-c74ac68f7892` using the `Card` request, should look up the invoice
in the database, construct `FakePayRequest` and pay via the external `fake_pay` service.

```
{
    "number": "1234 5656 7822 5678",
    "expiry": "01-2040",
    "name": "Work Card"
}

```
Should produce the following `InvoiceResponse` with the card marked.

```
201,
{
    "id": "8176929e-5484-462b-9758-c74ac68f7892",
    "jobDescription": "Building Payment System",
    "customerId": 3,
    "amount": 299.99,
    "card": {
        "number": "123456********5678",
        "expiry": "01-2040",
        "name": "Work Card"
    },
    "customerName": "Seth Hall",
    "customerEmail": "seth.hall@paymark.co.nz",
    "invoiceStatus": "PAID"
}
```
Handle any issues where invoice doesn't exist, bad card requests, or non PENDING status 


### 3) GET: /invoices 
returns all invoices as an array of 'InvoiceResponse' and has an optional query parameter filter by an 'invoiceStatus'  (eg PAID, PENDING, CANCELLED) 

eg: 
```
GET /invoices?invoiceStatus=PENDING
```

Will return a list of `InvoiceResponse`

```
200,
[
    {
        "jobDescription": "SEO Optimization",
        "customerId": 3,
        "amount": 175.0,
        "id": "6f53c715-0369-11f0-8d97-7c646cb7c0bc",
        "customerName": "Seth Hall",
        "customerEmail": "seth.hall@paymark.co.nz",
        "invoiceStatus": "PENDING"
    },
    {
        "jobDescription": "Consultation Service",
        "customerId": 3,
        "amount": 300.25,
        "id": "6f53c7be-0369-11f0-8d97-7c646cb7c0bc",
        "customerName": "Seth Hall",
        "customerEmail": "seth.hall@paymark.co.nz",
        "invoiceStatus": "PENDING"
    },
    {
        "jobDescription": "Testing full",
        "customerId": 1,
        "amount": 119.99,
        "id": "a4757465-d1d4-485a-afe9-b3bf65b96801",
        "customerName": "John Doe",
        "customerEmail": "john.doe@example.com",
        "invoiceStatus": "PENDING"
    }
]
```
Think about how you could handle a large amount of data - perhaps we only want to give back 10 invoices at a time. Handle this scenario with an appropriate solution.

#### PLEASE Comment your code and adhere to Python best practices where possible and use an appropriate logger for debug and important steps ####

### For all tasks think about error scenarios and how to handle any unexpected situations ###
